//! Rust port of jarvis/tools.py's Codex CLI delegation:
//! `codex_delegate_plan` (plan builder), `run_codex_delegate` (synchronous
//! delegated coding run), and `run_codex_chat` (quick read-only conversational
//! run). The plan/execute split from Python is preserved on purpose:
//! [`delegate_plan`] only builds the command line (so a caller can preview it),
//! while [`delegate_execute`] actually spawns the subprocess.
//!
//! Two safety properties from the Python original are preserved here:
//!   1. The read-only path (`write_capable: false`) is the default and always
//!      sets `--sandbox read-only --ask-for-approval never`.
//!   2. The write-capable path (`--sandbox workspace-write`) can only be reached
//!      through [`DelegateMode::WriteCapable`], which carries a
//!      [`ConfirmationToken`]. In Python the typed-confirmation gate lives one
//!      layer up (jarvis/safety.py + jarvis/planner.py) and `tools.py` will
//!      happily execute a write plan if asked. Because jarvis-server's
//!      `/api/plan` + `/api/command` routing is still stubbed in this port,
//!      there is currently NO caller enforcing that gate -- so the token exists
//!      as structural defense-in-depth: you cannot request a write-capable run
//!      without naming the confirmation at the call site. See
//!      [`ConfirmationToken`] and [`DelegateMode`].
//!
//! NOT PORTED (out of scope for this pass): the async fire-and-forget job system
//! (`start_codex_delegate_job` / `start_codex_continue_job` and the
//! `CODEX_JOBS` registry), Codex proxy env plumbing (`_codex_child_env`), and
//! prompt shaping (`_clean_codex_prompt` / `_codex_fast_prompt`). Prompts are
//! passed through verbatim.

use jarvis_config::CodexConfig;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use tokio::process::Command as TokioCommand;

/// Python truncates delegate stdout to ~8000 chars and stderr to ~3000 (see
/// jarvis/tools.py:18515-18516). Chat uses a tighter 4000/1500 budget.
const DELEGATE_STDOUT_MAX: usize = 8000;
const DELEGATE_STDERR_MAX: usize = 3000;
const CHAT_STDOUT_MAX: usize = 4000;
const CHAT_STDERR_MAX: usize = 1500;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum Sandbox {
    ReadOnly,
    WorkspaceWrite,
}

impl Sandbox {
    fn as_flag(self) -> &'static str {
        match self {
            Sandbox::ReadOnly => "read-only",
            Sandbox::WorkspaceWrite => "workspace-write",
        }
    }
}

/// Proof that a caller resolved Jarvis's typed-confirmation gate
/// (jarvis-safety's `RiskLevel::ExternalDestructiveSensitive`) before requesting
/// a write-capable Codex delegation.
///
/// This crate deliberately cannot *verify* the gate -- the confirmation prompt
/// lives one layer up, in server handlers that are still stubbed in this port.
/// The token therefore exists purely to make it structurally awkward to launch
/// a write-capable run: a caller has to construct one explicitly, which forces
/// the confirmation to be named at the call site and makes any fabricated
/// approval obvious in review. Constructing a token is the caller asserting
/// "I already obtained typed confirmation from the user."
#[derive(Debug, Clone, Copy)]
pub struct ConfirmationToken {
    _private: (),
}

impl ConfirmationToken {
    /// Assert that the typed-confirmation gate was resolved by the caller. Named
    /// loudly on purpose so any call site that manufactures one stands out.
    pub fn confirmed_by_caller() -> Self {
        ConfirmationToken { _private: () }
    }
}

/// Selects the sandbox for [`delegate_execute`]. The write-capable variant can
/// only be built with a [`ConfirmationToken`], so the type system alone
/// prevents a write-capable delegation from being requested without an explicit
/// confirmation at the call site.
#[derive(Debug, Clone, Copy)]
pub enum DelegateMode {
    /// `--sandbox read-only`. Always safe; the default.
    ReadOnly,
    /// `--sandbox workspace-write`. Requires proof of typed confirmation.
    WriteCapable(ConfirmationToken),
}

impl DelegateMode {
    fn write_capable(self) -> bool {
        matches!(self, DelegateMode::WriteCapable(_))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodexPlan {
    pub tool: &'static str,
    pub available: bool,
    pub codex_path: Option<PathBuf>,
    pub model: String,
    pub sandbox: String,
    pub write_capable: bool,
    pub planned_command: Vec<String>,
    pub status: &'static str,
}

/// Outcome of a delegate/chat run, mirroring the dict shape returned by
/// `run_codex_delegate` / `run_codex_chat` in jarvis/tools.py.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ExecStatus {
    /// The `codex` executable could not be located (Python: `codex_not_found`).
    CodexNotFound,
    /// Ran to completion with exit code 0.
    Completed,
    /// Ran to completion with a non-zero exit code.
    Failed,
    /// Killed after exceeding the configured timeout.
    Timeout,
    /// The process could not be started, or an I/O error occurred while waiting.
    ExecutionError,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodexExecution {
    pub tool: &'static str,
    pub available: bool,
    pub codex_path: Option<PathBuf>,
    pub model: String,
    pub sandbox: String,
    pub write_capable: bool,
    pub status: ExecStatus,
    pub executed: bool,
    pub exit_code: Option<i32>,
    pub stdout: String,
    pub stderr: String,
    pub last_message: String,
    pub error: Option<String>,
    pub duration_seconds: f64,
    pub duration_human: String,
    pub reply: String,
}

impl CodexExecution {
    fn base(plan: &CodexPlan, status: ExecStatus, executed: bool, duration: f64) -> Self {
        CodexExecution {
            tool: plan.tool,
            available: plan.available,
            codex_path: plan.codex_path.clone(),
            model: plan.model.clone(),
            sandbox: plan.sandbox.clone(),
            write_capable: plan.write_capable,
            status,
            executed,
            exit_code: None,
            stdout: String::new(),
            stderr: String::new(),
            last_message: String::new(),
            error: None,
            duration_seconds: round3(duration),
            duration_human: format_seconds(duration),
            reply: String::new(),
        }
    }

    fn not_found(plan: &CodexPlan) -> Self {
        let mut exec = Self::base(plan, ExecStatus::CodexNotFound, false, 0.0);
        exec.reply = "Codex CLI is not available on this machine.".to_string();
        exec
    }
}

/// Mirrors `codex_delegate_plan()` (jarvis/tools.py:16396). Builds the command
/// line only -- does not execute anything. `write_capable` selects
/// `--sandbox workspace-write` instead of the always-safe `read-only` default;
/// callers MUST have already gated this behind typed confirmation (see
/// [`delegate_execute`] / [`ConfirmationToken`]).
pub fn delegate_plan(
    prompt: &str,
    project_dir: &Path,
    config: &CodexConfig,
    write_capable: bool,
) -> CodexPlan {
    let codex_path = crate::find_executable("codex");
    let sandbox = if write_capable {
        Sandbox::WorkspaceWrite
    } else {
        Sandbox::ReadOnly
    };
    let mut command = vec![
        codex_path
            .as_ref()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|| "codex".to_string()),
        "--model".to_string(),
        config.model.clone(),
        "-c".to_string(),
        format!("model_reasoning_effort={}", config.reasoning_effort),
        "--sandbox".to_string(),
        sandbox.as_flag().to_string(),
        "--ask-for-approval".to_string(),
        "never".to_string(),
        "exec".to_string(),
        "--cd".to_string(),
        project_dir.display().to_string(),
        "--skip-git-repo-check".to_string(),
    ];
    command.push(prompt.to_string());

    CodexPlan {
        tool: if write_capable {
            "codex.delegate_write"
        } else {
            "codex.delegate"
        },
        available: codex_path.is_some(),
        codex_path,
        model: config.model.clone(),
        sandbox: sandbox.as_flag().to_string(),
        write_capable,
        planned_command: command,
        status: "dry_run",
    }
}

/// Mirrors `run_codex_delegate()` (jarvis/tools.py:18459): builds the plan, then
/// actually runs `codex exec ...` as an async subprocess with an
/// `--output-last-message` temp file and a hard timeout.
///
/// The [`DelegateMode`] argument is what enforces the write-capable safety
/// property: reaching `--sandbox workspace-write` requires
/// [`DelegateMode::WriteCapable`], which cannot be constructed without a
/// [`ConfirmationToken`]. See the module docs for why.
pub async fn delegate_execute(
    prompt: &str,
    project_dir: &Path,
    config: &CodexConfig,
    mode: DelegateMode,
) -> CodexExecution {
    let plan = delegate_plan(prompt, project_dir, config, mode.write_capable());
    if !plan.available {
        return CodexExecution::not_found(&plan);
    }
    let timeout = Duration::from_secs(config.timeout_seconds as u64);
    execute_plan(
        &plan,
        project_dir,
        timeout,
        DELEGATE_STDOUT_MAX,
        DELEGATE_STDERR_MAX,
    )
    .await
}

/// Mirrors `run_codex_chat()` (jarvis/tools.py:16442): a simpler, ALWAYS
/// read-only conversational run using the shorter `chat_timeout_seconds`. There
/// is deliberately no write-capable variant of chat.
pub async fn chat(prompt: &str, project_dir: &Path, config: &CodexConfig) -> CodexExecution {
    let plan = delegate_plan(prompt, project_dir, config, false);
    let timeout = Duration::from_secs(config.chat_timeout_seconds as u64);
    let mut exec = if plan.available {
        execute_plan(
            &plan,
            project_dir,
            timeout,
            CHAT_STDOUT_MAX,
            CHAT_STDERR_MAX,
        )
        .await
    } else {
        CodexExecution::not_found(&plan)
    };
    exec.tool = "conversation.codex";
    exec
}

async fn execute_plan(
    plan: &CodexPlan,
    cwd: &Path,
    timeout: Duration,
    stdout_max: usize,
    stderr_max: usize,
) -> CodexExecution {
    let started = Instant::now();
    let temp_dir = match tempfile::tempdir() {
        Ok(dir) => dir,
        Err(error) => {
            let mut exec = CodexExecution::base(
                plan,
                ExecStatus::ExecutionError,
                false,
                started.elapsed().as_secs_f64(),
            );
            exec.error = Some(error.to_string());
            exec.reply = format!("I could not start Codex CLI: {error}");
            return exec;
        }
    };
    let output_path = temp_dir.path().join("last-message.txt");

    // Insert `--output-last-message <path>` just before the prompt (the final
    // arg), matching the splice in run_codex_delegate (tools.py:18473-18478).
    let mut command = plan.planned_command.clone();
    let prompt_arg = command.pop().unwrap_or_default();
    command.push("--output-last-message".to_string());
    command.push(output_path.display().to_string());
    command.push(prompt_arg);

    let outcome = run_command(&command, cwd, timeout).await;
    let duration = started.elapsed().as_secs_f64();

    if let Some(error) = outcome.spawn_error {
        let mut exec = CodexExecution::base(plan, ExecStatus::ExecutionError, false, duration);
        exec.error = Some(error.clone());
        exec.reply = format!("I could not start Codex CLI: {error}");
        return exec;
    }

    if outcome.timed_out {
        let mut exec = CodexExecution::base(plan, ExecStatus::Timeout, true, duration);
        exec.reply = format!(
            "Codex CLI timed out after {} seconds using {}.",
            timeout.as_secs(),
            plan.model
        );
        return exec;
    }

    let last_message = tokio::fs::read_to_string(&output_path)
        .await
        .map(|text| text.trim().to_string())
        .unwrap_or_default();
    let stdout = text_tail(&outcome.stdout, stdout_max);
    let stderr = text_tail(&outcome.stderr, stderr_max);
    let status = if outcome.exit_code == Some(0) {
        ExecStatus::Completed
    } else {
        ExecStatus::Failed
    };
    let reply = codex_reply(
        &stdout,
        &stderr,
        outcome.exit_code,
        &plan.model,
        &last_message,
    );

    let mut exec = CodexExecution::base(plan, status, true, duration);
    exec.exit_code = outcome.exit_code;
    exec.stdout = stdout;
    exec.stderr = stderr;
    exec.last_message = last_message;
    exec.reply = reply;
    exec
}

/// Raw result of a single subprocess invocation. Kept separate from
/// [`CodexExecution`] so the process-running logic can be tested against
/// arbitrary commands (e.g. `sleep`) without depending on `codex` being present.
struct RawOutcome {
    timed_out: bool,
    exit_code: Option<i32>,
    stdout: String,
    stderr: String,
    /// Set when the process could not be spawned, or an I/O error occurred while
    /// waiting for it (Python's `OSError` path).
    spawn_error: Option<String>,
}

/// Runs `command` (element 0 is the program, the rest are args) in `cwd`,
/// enforcing `timeout` via [`tokio::time::timeout`]. `kill_on_drop(true)` ensures
/// the child is killed when the timeout future is dropped, so a runaway process
/// cannot outlive its deadline.
async fn run_command(command: &[String], cwd: &Path, timeout: Duration) -> RawOutcome {
    let Some((program, args)) = command.split_first() else {
        return RawOutcome {
            timed_out: false,
            exit_code: None,
            stdout: String::new(),
            stderr: String::new(),
            spawn_error: Some("empty command".to_string()),
        };
    };

    let mut cmd = TokioCommand::new(program);
    cmd.args(args)
        .current_dir(cwd)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);

    let child = match cmd.spawn() {
        Ok(child) => child,
        Err(error) => {
            return RawOutcome {
                timed_out: false,
                exit_code: None,
                stdout: String::new(),
                stderr: String::new(),
                spawn_error: Some(error.to_string()),
            };
        }
    };

    match tokio::time::timeout(timeout, child.wait_with_output()).await {
        Ok(Ok(output)) => RawOutcome {
            timed_out: false,
            exit_code: output.status.code(),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            spawn_error: None,
        },
        Ok(Err(error)) => RawOutcome {
            timed_out: false,
            exit_code: None,
            stdout: String::new(),
            stderr: String::new(),
            spawn_error: Some(error.to_string()),
        },
        // Deadline hit: dropping the `wait_with_output` future drops the child,
        // which (kill_on_drop) sends SIGKILL.
        Err(_elapsed) => RawOutcome {
            timed_out: true,
            exit_code: None,
            stdout: String::new(),
            stderr: String::new(),
            spawn_error: None,
        },
    }
}

/// Mirrors `_text_tail` (jarvis/tools.py:6676): keep the last `max_chars`
/// characters. Counts by `char` (Unicode scalar values) to avoid splitting a
/// multi-byte character mid-way.
fn text_tail(value: &str, max_chars: usize) -> String {
    let count = value.chars().count();
    if count <= max_chars {
        value.to_string()
    } else {
        value.chars().skip(count - max_chars).collect()
    }
}

/// Mirrors `_codex_reply` (jarvis/tools.py:21645).
fn codex_reply(
    stdout: &str,
    stderr: &str,
    exit_code: Option<i32>,
    model: &str,
    last_message: &str,
) -> String {
    if exit_code == Some(0) {
        let last = last_message.trim();
        if !last.is_empty() {
            return text_tail(last, 4000);
        }
        let content = stdout.trim();
        if content.is_empty() {
            return format!("Codex CLI finished with {model}, but it did not return visible text.");
        }
        return text_tail(content, 1800);
    }
    let mut error = stderr.trim();
    if error.is_empty() {
        error = stdout.trim();
    }
    if error.is_empty() {
        let code = exit_code
            .map(|c| c.to_string())
            .unwrap_or_else(|| "unknown".to_string());
        return format!("Codex CLI failed using {model}: exit code {code}");
    }
    format!("Codex CLI failed using {model}: {}", text_tail(error, 1200))
}

/// Mirrors `_format_seconds` (jarvis/tools.py:21615).
fn format_seconds(seconds: f64) -> String {
    if seconds < 60.0 {
        format!("{seconds:.1}s")
    } else {
        let minutes = (seconds / 60.0).floor() as u64;
        let remainder = seconds - (minutes as f64) * 60.0;
        format!("{minutes}m {remainder:.1}s")
    }
}

fn round3(value: f64) -> f64 {
    (value.max(0.0) * 1000.0).round() / 1000.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use jarvis_config::Config;

    fn test_config() -> Config {
        Config::load()
    }

    #[test]
    fn read_only_default_sets_read_only_sandbox() {
        let config = test_config();
        let plan = delegate_plan("test prompt", Path::new("/tmp"), &config.codex, false);
        assert_eq!(plan.sandbox, "read-only");
        assert!(!plan.write_capable);
        assert_eq!(plan.tool, "codex.delegate");
    }

    #[test]
    fn write_capable_sets_workspace_write_sandbox() {
        let config = test_config();
        let plan = delegate_plan("test prompt", Path::new("/tmp"), &config.codex, true);
        assert_eq!(plan.sandbox, "workspace-write");
        assert!(plan.write_capable);
        assert_eq!(plan.tool, "codex.delegate_write");
    }

    #[test]
    fn write_capable_mode_requires_confirmation_token() {
        // Read-only needs no token.
        assert!(!DelegateMode::ReadOnly.write_capable());
        // Reaching write-capable requires constructing a ConfirmationToken --
        // this call would not compile without one, which is the whole point.
        let mode = DelegateMode::WriteCapable(ConfirmationToken::confirmed_by_caller());
        assert!(mode.write_capable());
    }

    #[test]
    fn not_found_is_graceful() {
        // Simulate `codex` being absent by hand-building an unavailable plan;
        // in this sandbox `codex` is actually installed, so we cannot rely on
        // find_executable("codex") returning None.
        let plan = CodexPlan {
            tool: "codex.delegate",
            available: false,
            codex_path: None,
            model: "test-model".to_string(),
            sandbox: "read-only".to_string(),
            write_capable: false,
            planned_command: vec!["codex".to_string(), "prompt".to_string()],
            status: "dry_run",
        };
        let exec = CodexExecution::not_found(&plan);
        assert_eq!(exec.status, ExecStatus::CodexNotFound);
        assert!(!exec.executed);
        assert!(!exec.available);
        assert!(exec.reply.contains("not available"));
    }

    #[tokio::test]
    async fn timeout_kills_long_running_child() {
        let started = Instant::now();
        let command = vec!["sleep".to_string(), "5".to_string()];
        let outcome = run_command(&command, Path::new("/tmp"), Duration::from_millis(200)).await;
        let elapsed = started.elapsed();
        assert!(outcome.timed_out, "expected the run to time out");
        assert!(outcome.spawn_error.is_none());
        // If the child were not killed we would have blocked for the full 5s.
        assert!(
            elapsed < Duration::from_secs(2),
            "timeout did not cancel promptly: {elapsed:?}"
        );
    }

    #[tokio::test]
    async fn spawn_failure_is_reported_gracefully() {
        let command = vec![
            "/nonexistent/definitely/not/a/real/binary".to_string(),
            "arg".to_string(),
        ];
        let outcome = run_command(&command, Path::new("/tmp"), Duration::from_secs(5)).await;
        assert!(!outcome.timed_out);
        assert!(outcome.spawn_error.is_some());
    }

    #[tokio::test]
    async fn empty_command_reports_spawn_error() {
        let outcome = run_command(&[], Path::new("/tmp"), Duration::from_secs(1)).await;
        assert!(outcome.spawn_error.is_some());
    }

    #[test]
    fn text_tail_keeps_last_chars() {
        assert_eq!(text_tail("hello world", 5), "world");
        assert_eq!(text_tail("short", 100), "short");
        // Multi-byte characters are not split.
        assert_eq!(text_tail("aébc", 3), "ébc");
    }

    #[test]
    fn codex_reply_prefers_last_message_on_success() {
        let reply = codex_reply("stdout text", "", Some(0), "m", "the last message");
        assert_eq!(reply, "the last message");
    }

    #[test]
    fn codex_reply_falls_back_to_stdout_then_placeholder() {
        assert_eq!(codex_reply("out", "", Some(0), "m", ""), "out");
        assert!(codex_reply("", "", Some(0), "m", "").contains("did not return visible text"));
    }

    #[test]
    fn codex_reply_reports_failure_with_stderr() {
        let reply = codex_reply("", "boom", Some(1), "m", "");
        assert!(reply.contains("failed"));
        assert!(reply.contains("boom"));
    }

    #[test]
    fn codex_reply_truncates_long_failure_output() {
        let long = "x".repeat(5000);
        let reply = codex_reply("", &long, Some(2), "m", "");
        // Tail is capped at 1200 chars; the prefix message adds a bounded amount.
        assert!(reply.chars().count() < 1400);
    }

    #[test]
    fn format_seconds_matches_python_shape() {
        assert_eq!(format_seconds(1.25), "1.2s");
        assert_eq!(format_seconds(65.0), "1m 5.0s");
    }

    #[tokio::test]
    async fn read_only_execution_runs_a_real_command() {
        // End-to-end exercise of execute_plan (spawn -> wait -> read output file
        // -> truncate) without invoking the real `codex`. `true` ignores every
        // argument and exits 0, so the spliced `--output-last-message <tmp>` and
        // prompt args are harmless.
        let plan = CodexPlan {
            tool: "codex.delegate",
            available: true,
            codex_path: Some(PathBuf::from("true")),
            model: "test-model".to_string(),
            sandbox: "read-only".to_string(),
            write_capable: false,
            planned_command: vec!["true".to_string(), "prompt".to_string()],
            status: "dry_run",
        };
        let exec = execute_plan(&plan, Path::new("/tmp"), Duration::from_secs(5), 100, 100).await;
        assert!(exec.executed);
        assert_eq!(exec.status, ExecStatus::Completed);
        assert_eq!(exec.exit_code, Some(0));
        // `true` writes nothing, so stdout stays empty and no output file exists.
        assert!(exec.stdout.is_empty());
        assert!(exec.last_message.is_empty());
    }
}
