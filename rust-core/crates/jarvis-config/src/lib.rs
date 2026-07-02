//! Mirrors `jarvis/config.py`: loads `~/.jarvis.env` (or `$JARVIS_ENV_FILE`) into the
//! process environment, then exposes typed config derived from `std::env`.

use std::collections::HashMap;
use std::env;
use std::fs;
use std::net::IpAddr;
use std::path::{Path, PathBuf};

/// Loads simple `KEY=VALUE` lines from the user env file into `std::env`, without
/// overwriting variables the process was already launched with. Blank lines and
/// lines starting with `#` are ignored. This intentionally never executes the file
/// (no shell, no `source`) -- same non-executing guarantee as the Python loader.
pub fn load_user_env_file() {
    let env_path = env::var("JARVIS_ENV_FILE").unwrap_or_else(|_| "~/.jarvis.env".to_string());
    let expanded = expand_home(&env_path);
    let Ok(contents) = fs::read_to_string(&expanded) else {
        return;
    };
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((key, value)) = trimmed.split_once('=') else {
            continue;
        };
        let key = key.trim();
        let value = value.trim();
        if key.is_empty() || env::var_os(key).is_some() {
            continue;
        }
        // Safety: single-threaded startup path only (called once, before the async
        // runtime and any other threads exist).
        unsafe {
            env::set_var(key, value);
        }
    }
}

fn expand_home(path: &str) -> PathBuf {
    if let Some(rest) = path.strip_prefix("~/") {
        if let Some(home) = env::var_os("HOME") {
            return Path::new(&home).join(rest);
        }
    }
    PathBuf::from(path)
}

fn env_bool(key: &str, default: bool) -> bool {
    match env::var(key) {
        Ok(v) => matches!(
            v.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        ),
        Err(_) => default,
    }
}

fn env_int(key: &str, default: u32, minimum: u32, maximum: u32) -> u32 {
    let parsed = env::var(key)
        .ok()
        .and_then(|v| v.trim().parse::<u32>().ok());
    parsed.unwrap_or(default).clamp(minimum, maximum)
}

fn env_string(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub host: IpAddr,
    pub port: u16,
    pub allow_non_loopback: bool,
}

#[derive(Debug, Clone)]
pub struct GroqConfig {
    pub api_key: String,
    pub base_url: String,
    pub fast_model: String,
}

#[derive(Debug, Clone)]
pub struct CodexConfig {
    pub model: String,
    pub reasoning_effort: String,
    pub timeout_seconds: u32,
    pub chat_timeout_seconds: u32,
    pub write_enabled: bool,
    pub user_name: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub server: ServerConfig,
    pub groq: GroqConfig,
    pub codex: CodexConfig,
    pub workspace_root: PathBuf,
    pub start_paused: bool,
    /// Raw snapshot of every JARVIS_*/GROQ_*/OPENAI_*-prefixed env var read at
    /// startup, for diagnostics endpoints -- never includes secret values.
    pub known_keys_present: HashMap<&'static str, bool>,
}

impl Config {
    pub fn load() -> Self {
        load_user_env_file();

        let host = env_string("JARVIS_HOST", "127.0.0.1")
            .parse::<IpAddr>()
            .unwrap_or_else(|_| IpAddr::from([127, 0, 0, 1]));
        let port = env_int("JARVIS_PORT", 8765, 1, 65535) as u16;
        let allow_non_loopback = env_bool("JARVIS_ALLOW_NON_LOOPBACK", false);

        let groq_api_key = env_string("GROQ_API_KEY", "");
        let mut known_keys_present = HashMap::new();
        known_keys_present.insert("GROQ_API_KEY", !groq_api_key.is_empty());

        let workspace_root = env::var("JARVIS_WORKSPACE_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));

        Config {
            server: ServerConfig {
                host,
                port,
                allow_non_loopback,
            },
            groq: GroqConfig {
                api_key: groq_api_key,
                base_url: env_string("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                fast_model: env_string("GROQ_FAST_MODEL", "llama-3.3-70b-versatile"),
            },
            codex: CodexConfig {
                // NOTE: matches jarvis/config.py:93 -- unverified model id, see that
                // file's inline comment. Confirm against `codex --model` output
                // before relying on this default.
                model: env_string("JARVIS_CODEX_MODEL", "gpt-5.4-mini"),
                reasoning_effort: env_string("JARVIS_CODEX_REASONING_EFFORT", "low"),
                timeout_seconds: env_int("JARVIS_CODEX_TIMEOUT_SECONDS", 210, 10, 300),
                chat_timeout_seconds: env_int("JARVIS_CODEX_CHAT_TIMEOUT_SECONDS", 12, 3, 90),
                write_enabled: env_bool("JARVIS_CODEX_WRITE_ENABLED", true),
                user_name: env::var("JARVIS_USER_NAME")
                    .ok()
                    .filter(|v| !v.trim().is_empty()),
            },
            workspace_root,
            start_paused: env_bool("JARVIS_START_PAUSED", false),
            known_keys_present,
        }
    }

    pub fn is_loopback_host(&self) -> bool {
        self.server.host.is_loopback()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn env_int_clamps_to_bounds() {
        assert_eq!(env_int("JARVIS_TEST_NONEXISTENT_KEY", 8765, 1, 65535), 8765);
    }

    #[test]
    fn expand_home_handles_tilde() {
        if let Some(home) = env::var_os("HOME") {
            let expanded = expand_home("~/.jarvis.env");
            assert_eq!(expanded, Path::new(&home).join(".jarvis.env"));
        }
    }
}
