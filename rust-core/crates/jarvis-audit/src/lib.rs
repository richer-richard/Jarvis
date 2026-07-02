//! Rust port of `jarvis/audit.py`: an append-only JSONL audit log that redacts
//! secrets before writing and trims itself by age and size.
//!
//! The redaction regexes (`SENSITIVE_TEXT_PATTERNS`, `STANDALONE_SECRET_PATTERNS`,
//! `SENSITIVE_DETAIL_KEY_PATTERN`) and the `redact_sensitive_text` /
//! `redact_audit_value` helpers mirror their Python counterparts so the on-disk
//! format (same field names, same `[REDACTED]` markers) is a drop-in match for
//! what `jarvis/audit.py` already writes -- a human or tool reading the log does
//! not need two different parsers.

use regex::{Captures, Regex};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::{SystemTime, UNIX_EPOCH};

/// Matches `AUDIT_MAX_STRING_CHARS` in jarvis/audit.py:36.
const AUDIT_MAX_STRING_CHARS: usize = 4000;

/// Mirrors `SENSITIVE_TEXT_PATTERNS` in jarvis/audit.py:18-26. Each is applied in
/// order via `redact_match` as a replacement callback.
static SENSITIVE_TEXT_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"(?i)\b([A-Za-z0-9_]*(?:api[_ -]?key|token|password|secret|credential)[A-Za-z0-9_]*)\s*[:=]\s*([^\s,;]+)").unwrap(),
        Regex::new(r"(?i)\b(api[_ -]?key|token|password|secret|credential)\s*[:=]\s*([^\s,;]+)").unwrap(),
        Regex::new(r"(?i)\b(api[_ -]?key|token|password|secret|credential)\s+is\s+([^\s,;]+)").unwrap(),
        Regex::new(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/\-]+=*").unwrap(),
    ]
});

/// Mirrors `STANDALONE_SECRET_PATTERNS` in jarvis/audit.py:27-31. These match
/// secret-shaped tokens with no surrounding key and are replaced wholesale.
static STANDALONE_SECRET_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"\bsk-[A-Za-z0-9_-]{8,}\b").unwrap(),
        Regex::new(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b").unwrap(),
        Regex::new(r"\bgithub_pat_[A-Za-z0-9_]{12,}\b").unwrap(),
    ]
});

/// Mirrors `SENSITIVE_DETAIL_KEY_PATTERN` in jarvis/audit.py:32-35. A structured
/// detail whose key matches has its entire value replaced with `[REDACTED]`.
static SENSITIVE_DETAIL_KEY_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(api[_ -]?key|authorization|bearer|credential|password|secret|token)").unwrap()
});

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEvent {
    pub id: String,
    pub timestamp: f64,
    pub command: String,
    pub risk_level: u8,
    pub risk_label: String,
    pub tool: String,
    pub decision: String,
    pub summary: String,
    pub details: Value,
}

impl AuditEvent {
    pub fn new(
        command: impl Into<String>,
        risk_level: u8,
        risk_label: impl Into<String>,
        tool: impl Into<String>,
        decision: impl Into<String>,
        summary: impl Into<String>,
    ) -> Self {
        AuditEvent {
            id: uuid::Uuid::new_v4().to_string(),
            timestamp: now_secs(),
            command: command.into(),
            risk_level,
            risk_label: risk_label.into(),
            tool: tool.into(),
            decision: decision.into(),
            summary: summary.into(),
            details: serde_json::json!({}),
        }
    }

    /// Returns a copy with secrets stripped from `command`, `summary`, and
    /// `details`, mirroring the redaction `jarvis/audit.py`'s `record()` applies
    /// before persisting. Structured fields (id/tool/decision/risk_*) are left
    /// as-is, matching the Python original.
    pub fn redacted(&self) -> AuditEvent {
        AuditEvent {
            id: self.id.clone(),
            timestamp: self.timestamp,
            command: redact_sensitive_text(&self.command),
            risk_level: self.risk_level,
            risk_label: self.risk_label.clone(),
            tool: self.tool.clone(),
            decision: self.decision.clone(),
            summary: redact_sensitive_text(&self.summary),
            details: redact_audit_value(&self.details),
        }
    }
}

/// Append-only JSONL audit log with age/size retention trimming, mirroring
/// `jarvis.audit.AuditLogger`.
pub struct AuditLogger {
    path: PathBuf,
    max_bytes: u64,
    retention_days: u64,
}

impl AuditLogger {
    /// Builds a logger whose retention limits come from the environment with the
    /// same defaults/clamps as jarvis/config.py:84-85
    /// (`JARVIS_AUDIT_RETENTION_DAYS` default 90 / min 1,
    /// `JARVIS_AUDIT_MAX_BYTES` default 1 GiB / min 1 MiB).
    pub fn new(path: impl AsRef<Path>) -> Self {
        AuditLogger {
            path: path.as_ref().to_path_buf(),
            max_bytes: audit_max_bytes(),
            retention_days: audit_retention_days(),
        }
    }

    /// Builds a logger with explicit limits, for tests and callers that manage
    /// their own retention policy.
    pub fn with_limits(path: impl AsRef<Path>, max_bytes: u64, retention_days: u64) -> Self {
        AuditLogger {
            path: path.as_ref().to_path_buf(),
            max_bytes,
            retention_days,
        }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Redacts secrets from `event` (see [`AuditEvent::redacted`]) and appends it
    /// as one JSONL line, then enforces retention. This is the safe replacement
    /// for the old `write_unredacted` placeholder: nothing hits disk unredacted.
    pub fn write(&self, event: &AuditEvent) -> anyhow::Result<()> {
        let redacted = event.redacted();
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        // Serialize through `to_value` so the object keys are emitted sorted,
        // matching jarvis/audit.py's `json.dumps(..., sort_keys=True)`.
        let line = serde_json::to_string(&serde_json::to_value(&redacted)?)?;
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        writeln!(file, "{line}")?;
        drop(file);
        self.enforce_retention()?;
        Ok(())
    }

    /// Trims events older than `retention_days` and then oldest-first until the
    /// file fits in `max_bytes`, mirroring jarvis/audit.py:159-181. Lines that
    /// are not parseable JSON (or whose timestamp is present-but-not-numeric) are
    /// preserved, exactly as the Python version does.
    pub fn enforce_retention(&self) -> anyhow::Result<()> {
        if !self.path.exists() {
            return Ok(());
        }
        let contents = std::fs::read_to_string(&self.path)?;
        let original: Vec<&str> = contents.lines().collect();
        let cutoff = now_secs() - (self.retention_days as f64) * 86_400.0;

        let mut kept: Vec<&str> = Vec::new();
        for line in &original {
            let keep = match serde_json::from_str::<Value>(line) {
                Ok(value) => match timestamp_of(&value) {
                    Timestamp::Numeric(ts) => ts >= cutoff,
                    Timestamp::Unconvertible => true,
                },
                Err(_) => true,
            };
            if keep {
                kept.push(line);
            }
        }

        // Byte budget matches Python: sum(len(line.encode("utf-8")) + 1).
        while byte_budget(&kept) > self.max_bytes && !kept.is_empty() {
            kept.remove(0);
        }

        if kept != original {
            let mut out = kept.join("\n");
            if !kept.is_empty() {
                out.push('\n');
            }
            std::fs::write(&self.path, out)?;
        }
        Ok(())
    }

    /// Reports whether the audit directory is writable without polluting the log:
    /// it ensures the parent directory exists, then writes and removes a
    /// throwaway probe file. Used by the server's `/api/self-check`.
    pub fn probe_writable(&self) -> bool {
        let Some(parent) = self.path.parent() else {
            return false;
        };
        if std::fs::create_dir_all(parent).is_err() {
            return false;
        }
        let probe = parent.join(format!(
            ".jarvis-audit-write-probe-{}",
            uuid::Uuid::new_v4()
        ));
        match std::fs::write(&probe, b"probe") {
            Ok(()) => {
                let _ = std::fs::remove_file(&probe);
                true
            }
            Err(_) => false,
        }
    }
}

enum Timestamp {
    Numeric(f64),
    Unconvertible,
}

/// Extracts a comparable timestamp from a parsed audit line, mirroring Python's
/// `float(event.get("timestamp", 0))` and its `TypeError`/`ValueError` fallback:
/// a missing field is treated as `0`, a numeric string is parsed, and any other
/// non-numeric value is reported as unconvertible (which keeps the line).
fn timestamp_of(value: &Value) -> Timestamp {
    match value.get("timestamp") {
        None => Timestamp::Numeric(0.0),
        Some(Value::Number(n)) => Timestamp::Numeric(n.as_f64().unwrap_or(0.0)),
        Some(Value::String(s)) => match s.trim().parse::<f64>() {
            Ok(parsed) => Timestamp::Numeric(parsed),
            Err(_) => Timestamp::Unconvertible,
        },
        Some(_) => Timestamp::Unconvertible,
    }
}

fn byte_budget(lines: &[&str]) -> u64 {
    lines.iter().map(|line| line.len() as u64 + 1).sum()
}

/// Applies every text/standalone pattern in sequence and truncates, mirroring
/// jarvis/audit.py:194-200.
pub fn redact_sensitive_text(text: &str) -> String {
    let mut redacted = text.to_string();
    for pattern in SENSITIVE_TEXT_PATTERNS.iter() {
        redacted = pattern.replace_all(&redacted, redact_match).into_owned();
    }
    for pattern in STANDALONE_SECRET_PATTERNS.iter() {
        redacted = pattern.replace_all(&redacted, "[REDACTED]").into_owned();
    }
    truncate_text(&redacted, AUDIT_MAX_STRING_CHARS)
}

/// Replacement callback for `SENSITIVE_TEXT_PATTERNS`, mirroring
/// jarvis/audit.py:203-208: keeps the matched key, normalizes the separator to
/// `=` (or ` is ` when the original phrasing used it), and redacts the value.
fn redact_match(caps: &Captures) -> String {
    let first = &caps[1];
    if first.eq_ignore_ascii_case("bearer") {
        return format!("{first} [REDACTED]");
    }
    let whole = caps.get(0).map(|m| m.as_str()).unwrap_or("");
    let separator = if whole.to_ascii_lowercase().contains(" is ") {
        " is "
    } else {
        "="
    };
    format!("{first}{separator}[REDACTED]")
}

/// Mirrors jarvis/audit.py:211-215: truncates by character count (not bytes) and
/// annotates how many characters were dropped.
fn truncate_text(text: &str, max_chars: usize) -> String {
    let char_count = text.chars().count();
    if char_count <= max_chars {
        return text.to_string();
    }
    let truncated: String = text.chars().take(max_chars).collect();
    let omitted = char_count - max_chars;
    format!("{truncated}...[truncated {omitted} chars]")
}

/// Recursively redacts a structured detail value, mirroring
/// jarvis/audit.py:218-234. Object keys are themselves redacted, and any value
/// under a sensitive key is replaced wholesale.
pub fn redact_audit_value(value: &Value) -> Value {
    match value {
        Value::String(s) => Value::String(redact_sensitive_text(s)),
        Value::Array(items) => Value::Array(items.iter().map(redact_audit_value).collect()),
        Value::Object(map) => {
            let mut out = serde_json::Map::new();
            for (key, child) in map {
                let redacted_key = redact_sensitive_text(key);
                let redacted_value = if is_sensitive_detail_key(key) {
                    Value::String("[REDACTED]".to_string())
                } else {
                    redact_audit_value(child)
                };
                out.insert(redacted_key, redacted_value);
            }
            Value::Object(out)
        }
        // Null / Bool / Number pass through unchanged, matching Python.
        other => other.clone(),
    }
}

fn is_sensitive_detail_key(key: &str) -> bool {
    SENSITIVE_DETAIL_KEY_PATTERN.is_match(key)
}

fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn env_u64(key: &str, default: u64) -> u64 {
    std::env::var(key)
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .unwrap_or(default)
}

fn audit_retention_days() -> u64 {
    env_u64("JARVIS_AUDIT_RETENTION_DAYS", 90).max(1)
}

fn audit_max_bytes() -> u64 {
    env_u64("JARVIS_AUDIT_MAX_BYTES", 1024 * 1024 * 1024).max(1024 * 1024)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn temp_path() -> PathBuf {
        std::env::temp_dir().join(format!("jarvis-audit-test-{}.jsonl", uuid::Uuid::new_v4()))
    }

    fn cleanup(path: &Path) {
        let _ = std::fs::remove_file(path);
    }

    fn sample_event(i: usize) -> AuditEvent {
        AuditEvent::new(
            format!("command number {i}"),
            0,
            "Local conversation",
            "conversation.local",
            "allowed",
            format!("summary {i}"),
        )
    }

    fn first_line(path: &Path) -> Value {
        let contents = std::fs::read_to_string(path).unwrap();
        let line = contents.lines().next().unwrap();
        serde_json::from_str(line).unwrap()
    }

    #[test]
    fn audit_event_round_trips_json() {
        let event = AuditEvent::new(
            "test command",
            0,
            "Local conversation",
            "conversation.fast_local",
            "allowed",
            "test summary",
        );
        let json = serde_json::to_string(&event).unwrap();
        let parsed: AuditEvent = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.command, "test command");
        assert_eq!(parsed.risk_level, 0);
    }

    #[test]
    fn redact_sensitive_text_examples() {
        assert_eq!(
            redact_sensitive_text("password: hunter2"),
            "password=[REDACTED]"
        );
        assert_eq!(
            redact_sensitive_text("api key is sk-abcd1234efgh"),
            "api key is [REDACTED]"
        );
        assert_eq!(
            redact_sensitive_text("bearer abc.def-token"),
            "bearer [REDACTED]"
        );
        assert_eq!(
            redact_sensitive_text("plain hello world"),
            "plain hello world"
        );
    }

    #[test]
    fn redact_sensitive_text_catches_standalone_github_token() {
        let redacted = redact_sensitive_text("pushed with ghp_ABCDEFGH12345678 today");
        assert!(!redacted.contains("ghp_ABCDEFGH12345678"));
        assert!(redacted.contains("[REDACTED]"));
    }

    #[test]
    fn truncates_overlong_text() {
        let long = "a".repeat(AUDIT_MAX_STRING_CHARS + 50);
        let redacted = redact_sensitive_text(&long);
        assert!(redacted.contains("[truncated 50 chars]"));
    }

    #[test]
    fn write_redacts_password_in_command() {
        let path = temp_path();
        let logger = AuditLogger::new(&path);
        let mut event = sample_event(0);
        event.command = "please set password: hunter2 now".to_string();
        logger.write(&event).unwrap();

        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(!contents.contains("hunter2"));
        assert!(contents.contains("[REDACTED]"));
        cleanup(&path);
    }

    #[test]
    fn write_redacts_token_shaped_string() {
        let path = temp_path();
        let logger = AuditLogger::new(&path);
        let mut event = sample_event(1);
        event.summary = "leaked ghp_ABCDEFGH12345678 in logs".to_string();
        logger.write(&event).unwrap();

        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(!contents.contains("ghp_ABCDEFGH12345678"));
        assert!(contents.contains("[REDACTED]"));
        cleanup(&path);
    }

    #[test]
    fn write_redacts_sensitive_detail_key() {
        let path = temp_path();
        let logger = AuditLogger::new(&path);
        let mut event = sample_event(2);
        event.details = json!({"authorization": "Bearer secret-abc", "note": "ok"});
        logger.write(&event).unwrap();

        let parsed = first_line(&path);
        assert_eq!(parsed["details"]["authorization"], "[REDACTED]");
        assert_eq!(parsed["details"]["note"], "ok");
        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(!contents.contains("secret-abc"));
        cleanup(&path);
    }

    #[test]
    fn write_normal_event_round_trips_unchanged() {
        let path = temp_path();
        let logger = AuditLogger::new(&path);
        let mut event = sample_event(3);
        event.command = "what time is it".to_string();
        event.summary = "It is noon".to_string();
        event.details = json!({"foo": "bar", "count": 3});
        logger.write(&event).unwrap();

        let parsed = first_line(&path);
        assert_eq!(parsed["command"], "what time is it");
        assert_eq!(parsed["summary"], "It is noon");
        assert_eq!(parsed["details"]["foo"], "bar");
        assert_eq!(parsed["details"]["count"], 3);
        assert_eq!(parsed["risk_level"], 0);
        assert_eq!(parsed["tool"], "conversation.local");
        cleanup(&path);
    }

    #[test]
    fn retention_trims_by_byte_cap() {
        let path = temp_path();
        // Write with generous limits so nothing is trimmed during the writes.
        let writer = AuditLogger::with_limits(&path, 10_000_000, 100_000);
        for i in 0..10 {
            writer.write(&sample_event(i)).unwrap();
        }
        assert_eq!(std::fs::read_to_string(&path).unwrap().lines().count(), 10);

        // Now enforce a tight byte cap and confirm oldest-first trimming.
        let trimmer = AuditLogger::with_limits(&path, 400, 100_000);
        trimmer.enforce_retention().unwrap();
        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(contents.len() as u64 <= 400);
        assert!(contents.lines().count() < 10);
        cleanup(&path);
    }

    #[test]
    fn retention_trims_events_older_than_cutoff() {
        let path = temp_path();
        let logger = AuditLogger::with_limits(&path, 10_000_000, 90);

        // An event stamped in 1970 is older than the 90-day cutoff and is dropped
        // by the enforce_retention() that runs after its own write.
        let mut old = sample_event(0);
        old.timestamp = 1000.0;
        logger.write(&old).unwrap();
        assert_eq!(std::fs::read_to_string(&path).unwrap().lines().count(), 0);

        // A fresh event survives.
        logger.write(&sample_event(1)).unwrap();
        let contents = std::fs::read_to_string(&path).unwrap();
        assert_eq!(contents.lines().count(), 1);
        assert!(contents.contains("summary 1"));
        cleanup(&path);
    }

    #[test]
    fn probe_writable_reports_true_for_writable_dir() {
        let path = temp_path();
        let logger = AuditLogger::new(&path);
        assert!(logger.probe_writable());
        // Probe must not create the log file itself.
        assert!(!path.exists());
        cleanup(&path);
    }
}
