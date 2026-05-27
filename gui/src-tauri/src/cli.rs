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

/// Resolve projects.toml the same way the CLI does: $PROJECTS_FILE wins,
/// else $MACHINE_CONFIG_DIR/projects.toml, else the dev checkout's
/// projects.toml, else ~/.config/machine/projects.toml.
pub fn projects_file() -> PathBuf {
    if let Ok(p) = std::env::var("PROJECTS_FILE") {
        return PathBuf::from(p);
    }
    if let Ok(dir) = std::env::var("MACHINE_CONFIG_DIR") {
        return PathBuf::from(dir).join("projects.toml");
    }
    if cfg!(debug_assertions) {
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../projects.toml");
        if dev.exists() {
            return dev;
        }
    }
    dirs::home_dir()
        .unwrap_or_default()
        .join(".config/machine/projects.toml")
}

/// The machine provisioning log directory (mirrors the CLI's STATE_DIR/logs).
pub fn log_dir() -> PathBuf {
    if let Ok(d) = std::env::var("MACHINE_STATE_DIR") {
        return PathBuf::from(d).join("logs");
    }
    if cfg!(debug_assertions) {
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.build/logs");
        if dev.exists() {
            return dev;
        }
    }
    dirs::home_dir()
        .unwrap_or_default()
        .join(".local/state/machine/logs")
}

pub const BUNDLED_PROFILES: &[&str] =
    &["cypress", "python", "rust", "go", "supabase-fly"];

/// Available profile names. In a dev checkout, read profiles/*.toml; otherwise
/// fall back to the known bundled set. (A future CLI `profiles --json` command
/// would let this stop guessing — tracked for a later pass.)
pub fn list_profile_names() -> Vec<String> {
    if cfg!(debug_assertions) {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../profiles");
        if let Ok(entries) = std::fs::read_dir(&dir) {
            let mut names: Vec<String> = entries
                .flatten()
                .filter_map(|e| {
                    let p = e.path();
                    if p.extension()?.to_str()? == "toml" {
                        Some(p.file_stem()?.to_string_lossy().to_string())
                    } else {
                        None
                    }
                })
                .collect();
            names.sort();
            if !names.is_empty() {
                return names;
            }
        }
    }
    BUNDLED_PROFILES.iter().map(|s| s.to_string()).collect()
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

    // Both behaviors live in one test on purpose: they mutate the process-global
    // MACHINE_BIN, so splitting them into separate #[test]s lets cargo's parallel
    // runner interleave set_var/remove_var and flake. One sequential test is
    // deterministic without pulling in a serial-test crate.
    #[test]
    fn machine_bin_resolution() {
        // $MACHINE_BIN wins when set.
        std::env::set_var("MACHINE_BIN", "/custom/machine");
        assert_eq!(machine_bin(), PathBuf::from("/custom/machine"));

        // With it unset: release → bare "machine"; debug → dev path IF it exists.
        // Both are acceptable — assert only that we get a non-empty path, no panic.
        std::env::remove_var("MACHINE_BIN");
        let p = machine_bin();
        assert!(!p.as_os_str().is_empty());
    }

    #[test]
    fn list_profile_names_nonempty() {
        // Dev checkout has profiles/*.toml; release falls back to BUNDLED_PROFILES.
        assert!(!list_profile_names().is_empty());
    }
}
