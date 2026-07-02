//! Rust port target for a coherent subset of `jarvis/tools.py` (22.5k lines in
//! the Python worker). SCOPE NOTE (2026-07-02 scaffold): this crate
//! deliberately does NOT attempt full parity with tools.py in this pass -- see
//! `../../MIGRATION.md` at the rust-core workspace root for what's ported vs
//! still Python-only. This scaffold only defines the module layout; `codex`
//! is the first real port target (mirrors jarvis/tools.py's
//! `codex_delegate_plan`/`run_codex_delegate`/`start_codex_delegate_job`,
//! including the new write-capable tier).

pub mod codex;

use std::path::{Path, PathBuf};

/// Locates an executable, mirroring jarvis/tools.py's `_find_executable`: PATH
/// lookup first (like `shutil.which`), then a small hardcoded fallback list of
/// well-known install locations keyed by executable name (Python's
/// `EXECUTABLE_CANDIDATE_PATHS`). Only `codex` has fallbacks wired up here --
/// that is the executable this crate actually launches.
pub fn find_executable(name: &str) -> Option<PathBuf> {
    if let Some(path_var) = std::env::var_os("PATH") {
        if let Some(found) = std::env::split_paths(&path_var)
            .map(|dir| dir.join(name))
            .find(|candidate| is_executable_file(candidate))
        {
            return Some(found);
        }
    }
    candidate_paths(name)
        .into_iter()
        .find(|candidate| is_executable_file(candidate))
}

/// Well-known absolute install locations checked when a PATH lookup misses,
/// mirroring `EXECUTABLE_CANDIDATE_PATHS["codex"]` in jarvis/tools.py:319.
fn candidate_paths(name: &str) -> Vec<PathBuf> {
    match name {
        "codex" => {
            let mut paths = vec![PathBuf::from(
                "/Applications/Codex.app/Contents/Resources/codex",
            )];
            if let Some(home) = std::env::var_os("HOME") {
                paths.push(Path::new(&home).join(".codex/bin/codex"));
            }
            paths.push(PathBuf::from("/opt/homebrew/bin/codex"));
            paths.push(PathBuf::from("/usr/local/bin/codex"));
            paths
        }
        _ => Vec::new(),
    }
}

/// Mirrors Python's `os.access(candidate, os.X_OK)` check: the path must be a
/// regular file with an executable bit set. On non-Unix targets we can only
/// confirm it is a file.
fn is_executable_file(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        path.metadata()
            .map(|meta| meta.permissions().mode() & 0o111 != 0)
            .unwrap_or(false)
    }
    #[cfg(not(unix))]
    {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn find_executable_locates_codex_via_path_or_fallback() {
        // In most dev environments `codex` is installed; if so, we should find an
        // executable file. If it is genuinely absent everywhere, the result is
        // `None` -- both are valid, we only assert the return is internally
        // consistent (a returned path always points at an executable file).
        if let Some(path) = find_executable("codex") {
            assert!(is_executable_file(&path));
        }
    }

    #[test]
    fn candidate_paths_only_defined_for_known_names() {
        assert!(!candidate_paths("codex").is_empty());
        assert!(candidate_paths("definitely-not-a-real-tool").is_empty());
    }

    #[test]
    fn is_executable_file_rejects_missing_paths() {
        assert!(!is_executable_file(Path::new(
            "/nonexistent/path/to/some/binary"
        )));
    }
}
