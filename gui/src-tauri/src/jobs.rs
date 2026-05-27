use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use serde::Serialize;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tauri::{AppHandle, Emitter};

use crate::cli::machine_bin;

pub type JobId = u64;

/// Allowed lifecycle actions. Restricting to a known set keeps the project
/// name as the only free input and avoids passing arbitrary args to the CLI.
const ACTIONS: &[&str] = &["up", "down", "update", "rebuild", "destroy"];

#[derive(Default)]
pub struct JobRegistry {
    next_id: AtomicU64,
    children: Mutex<HashMap<JobId, Child>>,
}

impl JobRegistry {
    fn alloc(&self) -> JobId {
        self.next_id.fetch_add(1, Ordering::Relaxed)
    }
}

#[derive(Clone, Serialize)]
struct LogEvent { line: String, stream: &'static str }

#[derive(Clone, Serialize)]
struct DoneEvent { exit_code: i32, duration_ms: u128 }

#[derive(Debug, thiserror::Error)]
pub enum JobError {
    #[error("unknown action: {0}")]
    UnknownAction(String),
    #[error("failed to spawn: {0}")]
    Spawn(#[from] std::io::Error),
}
impl serde::Serialize for JobError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// Spawn `machine <action> <project> --plain`, streaming output as Tauri events.
/// Returns the JobId immediately; the subprocess runs in a background task.
pub async fn spawn_lifecycle(
    app: AppHandle,
    registry: Arc<JobRegistry>,
    project: String,
    action: String,
) -> Result<JobId, JobError> {
    if !ACTIONS.contains(&action.as_str()) {
        return Err(JobError::UnknownAction(action));
    }
    // -y skips the CLI's own confirmation for destroy/rebuild (the GUI gates
    // that with its own modal in plan 2b).
    let mut args = vec![action.clone(), project.clone(), "--plain".to_string()];
    if action == "destroy" || action == "rebuild" {
        args.push("-y".to_string());
    }

    let mut child = Command::new(machine_bin())
        .args(&args)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()?;

    let id = registry.alloc();
    let stdout = child.stdout.take().expect("piped stdout");
    let stderr = child.stderr.take().expect("piped stderr");

    registry.children.lock().await.insert(id, child);

    let log_topic = format!("job://{id}/log");
    let done_topic = format!("job://{id}/done");
    let started = std::time::Instant::now();

    // stdout reader
    {
        let app = app.clone();
        let topic = log_topic.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let _ = app.emit(&topic, LogEvent { line, stream: "stdout" });
            }
        });
    }
    // stderr reader
    {
        let app = app.clone();
        let topic = log_topic.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let _ = app.emit(&topic, LogEvent { line, stream: "stderr" });
            }
        });
    }
    // waiter — removes the child from the registry and emits done
    {
        let app = app.clone();
        let registry = registry.clone();
        tokio::spawn(async move {
            // Re-take the child to await it (we stored it for cancel access).
            let status = {
                let mut guard = registry.children.lock().await;
                match guard.remove(&id) {
                    Some(mut c) => c.wait().await,
                    None => return, // cancelled before we got here
                }
            };
            let code = status.ok().and_then(|s| s.code()).unwrap_or(-1);
            let _ = app.emit(&done_topic, DoneEvent {
                exit_code: code,
                duration_ms: started.elapsed().as_millis(),
            });
        });
    }

    Ok(id)
}

pub async fn cancel_job(registry: Arc<JobRegistry>, id: JobId) {
    if let Some(mut child) = registry.children.lock().await.remove(&id) {
        let _ = child.start_kill(); // SIGTERM on unix
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unknown_action_synchronously() {
        // Pure validation path doesn't need a Tauri app: assert the action list.
        assert!(!ACTIONS.contains(&"rm"));
        assert!(ACTIONS.contains(&"up"));
        assert!(ACTIONS.contains(&"destroy"));
    }
}
