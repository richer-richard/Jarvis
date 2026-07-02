//! Credential persistence at `~/.jarvis/auth/openai_oauth.json`.
//!
//! Hard requirements from the design doc (§5): file mode `0600`, parent dir
//! `0700`, atomic write (temp file + rename), and a path that can NEVER collide
//! with `~/.codex/auth.json`. This crate never reads or writes anything under
//! `~/.codex/`.

use crate::error::{OAuthError, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Jarvis's own on-disk credential shape (deliberately NOT Codex's `AuthDotJson`).
/// `id_token` is kept raw so `account_id` can be re-derived on load if needed.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StoredCredentials {
    pub access_token: String,
    pub refresh_token: String,
    pub id_token: String,
    pub account_id: Option<String>,
    /// Absolute expiry; drives the 5-minute eager-refresh window.
    pub expires_at: DateTime<Utc>,
    /// When these tokens were last minted; drives the ~8-day proactive refresh.
    pub last_refresh: DateTime<Utc>,
    /// Which client_id minted this (forward-compat if OpenAI ever rotates it).
    pub client_id: String,
    pub scopes: String,
}

/// A handle to the credential file. Constructed either at the default location
/// or at an explicit path (used by tests).
pub struct Storage {
    path: PathBuf,
}

impl Storage {
    /// Points at an explicit file path.
    pub fn at(path: impl Into<PathBuf>) -> Self {
        Storage { path: path.into() }
    }

    /// Points at `~/.jarvis/auth/openai_oauth.json`, resolving `$HOME`.
    pub fn default_location() -> Result<Self> {
        Ok(Storage {
            path: default_path()?,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Reads and deserializes the credentials, or `Ok(None)` if the file does not
    /// exist yet (not-authenticated is not an error at this layer).
    pub fn load(&self) -> Result<Option<StoredCredentials>> {
        let bytes = match std::fs::read(&self.path) {
            Ok(bytes) => bytes,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(OAuthError::Storage(e)),
        };
        let creds = serde_json::from_slice(&bytes).map_err(OAuthError::Serde)?;
        Ok(Some(creds))
    }

    /// Atomically writes the credentials with `0600`, ensuring the parent dir
    /// exists with `0700`. Writes to a uniquely-named temp file in the same
    /// directory and renames it over the target so a reader never observes a
    /// half-written file.
    pub fn save(&self, creds: &StoredCredentials) -> Result<()> {
        let parent = self
            .path
            .parent()
            .ok_or_else(|| OAuthError::Storage(other_io("credential path has no parent dir")))?;
        std::fs::create_dir_all(parent).map_err(OAuthError::Storage)?;
        harden_dir(parent)?;

        let json = serde_json::to_vec_pretty(creds).map_err(OAuthError::Serde)?;

        let tmp = parent.join(format!(
            ".openai_oauth.json.tmp-{}",
            crate::pkce::random_urlsafe(9)
        ));
        write_private(&tmp, &json).map_err(|e| {
            let _ = std::fs::remove_file(&tmp);
            OAuthError::Storage(e)
        })?;
        std::fs::rename(&tmp, &self.path).map_err(|e| {
            let _ = std::fs::remove_file(&tmp);
            OAuthError::Storage(e)
        })?;
        Ok(())
    }

    /// Removes the credential file (logout). Absent file is treated as success.
    pub fn delete(&self) -> Result<()> {
        match std::fs::remove_file(&self.path) {
            Ok(()) => Ok(()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(e) => Err(OAuthError::Storage(e)),
        }
    }
}

/// `~/.jarvis/auth/openai_oauth.json`.
pub fn default_path() -> Result<PathBuf> {
    Ok(default_auth_dir()?.join("openai_oauth.json"))
}

/// `~/.jarvis/auth`.
pub fn default_auth_dir() -> Result<PathBuf> {
    let home = std::env::var_os("HOME").ok_or(OAuthError::NoHome)?;
    Ok(PathBuf::from(home).join(".jarvis").join("auth"))
}

fn other_io(msg: &str) -> std::io::Error {
    std::io::Error::other(msg)
}

/// Writes `bytes` to `path`, creating the file with `0600` on Unix from the
/// outset (so the secret is never briefly world-readable), and fsyncing before
/// close.
fn write_private(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    use std::io::Write as _;

    let mut opts = std::fs::OpenOptions::new();
    opts.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        opts.mode(0o600);
    }
    let mut file = opts.open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

/// Tightens the auth directory to `0700` on Unix. `create_dir_all` respects the
/// umask, so we set the mode explicitly after creation. No-op on non-Unix.
fn harden_dir(dir: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        let perms = std::fs::Permissions::from_mode(0o700);
        std::fs::set_permissions(dir, perms).map_err(OAuthError::Storage)?;
    }
    #[cfg(not(unix))]
    {
        let _ = dir;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    fn sample_creds() -> StoredCredentials {
        let now = Utc::now();
        StoredCredentials {
            access_token: "at-abc".to_string(),
            refresh_token: "rt-def".to_string(),
            id_token: "a.b.c".to_string(),
            account_id: Some("acc_123".to_string()),
            expires_at: now + Duration::hours(1),
            last_refresh: now,
            client_id: crate::authorize::CLIENT_ID.to_string(),
            scopes: crate::authorize::SCOPES.to_string(),
        }
    }

    #[test]
    fn save_then_load_round_trips() {
        let dir = tempfile::tempdir().unwrap();
        let storage = Storage::at(dir.path().join("auth").join("openai_oauth.json"));
        let creds = sample_creds();
        storage.save(&creds).unwrap();
        let loaded = storage.load().unwrap().unwrap();
        assert_eq!(loaded, creds);
    }

    #[test]
    fn load_missing_file_is_none() {
        let dir = tempfile::tempdir().unwrap();
        let storage = Storage::at(dir.path().join("nope.json"));
        assert!(storage.load().unwrap().is_none());
    }

    #[test]
    fn delete_removes_file_and_is_idempotent() {
        let dir = tempfile::tempdir().unwrap();
        let storage = Storage::at(dir.path().join("auth").join("openai_oauth.json"));
        storage.save(&sample_creds()).unwrap();
        assert!(storage.path().exists());
        storage.delete().unwrap();
        assert!(!storage.path().exists());
        // Deleting again is a no-op success.
        storage.delete().unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn file_is_0600_and_dir_is_0700() {
        use std::os::unix::fs::PermissionsExt as _;
        let dir = tempfile::tempdir().unwrap();
        let auth_dir = dir.path().join("auth");
        let storage = Storage::at(auth_dir.join("openai_oauth.json"));
        storage.save(&sample_creds()).unwrap();

        let file_mode = std::fs::metadata(storage.path())
            .unwrap()
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(file_mode, 0o600, "credential file must be 0600");

        let dir_mode = std::fs::metadata(&auth_dir).unwrap().permissions().mode() & 0o777;
        assert_eq!(dir_mode, 0o700, "auth dir must be 0700");
    }

    #[test]
    fn save_overwrites_existing_atomically() {
        let dir = tempfile::tempdir().unwrap();
        let storage = Storage::at(dir.path().join("auth").join("openai_oauth.json"));
        storage.save(&sample_creds()).unwrap();

        let mut updated = sample_creds();
        updated.access_token = "at-rotated".to_string();
        storage.save(&updated).unwrap();

        let loaded = storage.load().unwrap().unwrap();
        assert_eq!(loaded.access_token, "at-rotated");
        // No temp files left behind.
        let leftovers: Vec<_> = std::fs::read_dir(dir.path().join("auth"))
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().contains(".tmp-"))
            .collect();
        assert!(leftovers.is_empty(), "temp files must be cleaned up");
    }
}
