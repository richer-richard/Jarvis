//! Mirrors the pause/mode slice of jarvis/server.py's `STATE` singleton
//! (server.py:607-640). Health/readiness/preflight/tool-registry/audit state are
//! NOT yet ported -- see rust-core/MIGRATION.md.

use jarvis_config::Config;
use serde_json::{json, Value};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

pub struct AppState {
    pub config: Config,
    mode: Mutex<ModeState>,
}

struct ModeState {
    paused: bool,
    reason: String,
    updated_at: f64,
}

impl AppState {
    pub fn new(config: Config) -> Self {
        let paused = config.start_paused;
        AppState {
            config,
            mode: Mutex::new(ModeState {
                paused,
                reason: if paused {
                    "JARVIS_START_PAUSED=1".to_string()
                } else {
                    String::new()
                },
                updated_at: now(),
            }),
        }
    }

    pub fn mode_snapshot(&self) -> Value {
        let mode = self.mode.lock().expect("mode mutex poisoned");
        json!({
            "paused": mode.paused,
            "reason": mode.reason,
            "updated_at": mode.updated_at,
            "commands_enabled": !mode.paused,
        })
    }

    pub fn set_mode(&self, paused: bool, reason: String) -> Value {
        let mut mode = self.mode.lock().expect("mode mutex poisoned");
        mode.paused = paused;
        mode.reason = reason;
        mode.updated_at = now();
        drop(mode);
        self.mode_snapshot()
    }
}

fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn set_mode_updates_paused_and_reason() {
        let state = AppState::new(Config::load());
        let snapshot = state.set_mode(true, "testing".to_string());
        assert_eq!(snapshot["paused"], true);
        assert_eq!(snapshot["reason"], "testing");
        assert_eq!(snapshot["commands_enabled"], false);
    }
}
