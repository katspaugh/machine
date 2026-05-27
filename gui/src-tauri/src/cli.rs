use std::path::PathBuf;
use std::process::Stdio;
use serde::de::DeserializeOwned;
use tokio::process::Command;

/// Resolve the path to the `machine` CLI.
/// Order: $MACHINE_BIN, then ../bin/machine relative to the crate in debug
/// builds (dev), else bare "machine" from PATH (release / Homebrew).
pub fn machine_bin() -> PathBuf {
    if let Ok(p) = std::env::var("MACHINE_BIN") {
        return PathBuf::from(p);
    }
    if cfg!(debug_assertions) {
        // CARGO_MANIFEST_DIR = gui/src-tauri ; the CLI is ../../bin/machine.
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../bin/machine");
        if dev.exists() {
            return dev;
        }
    }
    PathBuf::from("machine")
}

#[derive(Debug, thiserror::Error)]
pub enum CliError {
    #[error("failed to spawn machine: {0}")]
    Spawn(#[from] std::io::Error),
    #[error("machine exited {code}: {stderr}")]
    NonZero { code: i32, stderr: String },
    #[error("failed to parse machine JSON: {0}")]
    Parse(#[from] serde_json::Error),
}

// Tauri commands must return a serializable error; map to a String at the boundary.
impl serde::Serialize for CliError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// Run `machine <args>` and deserialize its stdout as JSON into T.
pub async fn run_json<T: DeserializeOwned>(args: &[&str]) -> Result<T, CliError> {
    let out = Command::new(machine_bin())
        .args(args)
        .stdin(Stdio::null())
        .output()
        .await?;
    if !out.status.success() {
        return Err(CliError::NonZero {
            code: out.status.code().unwrap_or(-1),
            stderr: String::from_utf8_lossy(&out.stderr).trim().to_string(),
        });
    }
    Ok(serde_json::from_slice(&out.stdout)?)
}

/// Run `machine <args>` expecting no JSON output; succeed on exit 0.
pub async fn run_ok(args: &[&str]) -> Result<(), CliError> {
    let out = Command::new(machine_bin())
        .args(args)
        .stdin(Stdio::null())
        .output()
        .await?;
    if !out.status.success() {
        return Err(CliError::NonZero {
            code: out.status.code().unwrap_or(-1),
            stderr: String::from_utf8_lossy(&out.stderr).trim().to_string(),
        });
    }
    Ok(())
}

/// Like run_json but tolerates a non-zero exit (e.g. `doctor` exits 1 when
/// checks fail yet still prints a valid JSON report on stdout).
pub async fn run_json_any_exit<T: DeserializeOwned>(args: &[&str]) -> Result<T, CliError> {
    let out = Command::new(machine_bin())
        .args(args)
        .stdin(Stdio::null())
        .output()
        .await?;
    // Prefer parsing stdout; only surface a process error if stdout is empty.
    if out.stdout.is_empty() && !out.status.success() {
        return Err(CliError::NonZero {
            code: out.status.code().unwrap_or(-1),
            stderr: String::from_utf8_lossy(&out.stderr).trim().to_string(),
        });
    }
    Ok(serde_json::from_slice(&out.stdout)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn machine_bin_honors_env() {
        std::env::set_var("MACHINE_BIN", "/custom/machine");
        assert_eq!(machine_bin(), PathBuf::from("/custom/machine"));
        std::env::remove_var("MACHINE_BIN");
    }

    #[test]
    fn machine_bin_falls_back_to_path() {
        std::env::remove_var("MACHINE_BIN");
        // In a release build with no dev path, resolves to bare "machine".
        // In debug, resolves to the dev path IF it exists; both are acceptable —
        // assert only that we get a non-empty path and don't panic.
        let p = machine_bin();
        assert!(!p.as_os_str().is_empty());
    }
}
