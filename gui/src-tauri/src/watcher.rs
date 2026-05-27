use std::path::PathBuf;
use std::time::Duration;
use notify::{RecommendedWatcher, RecursiveMode, Watcher, EventKind};
use tauri::{AppHandle, Emitter};

use crate::cli;
use crate::types::ProjectStatus;

/// Watch projects.toml; on any modify/create event, re-query ps --json and
/// emit projects://updated. Debounced by coalescing rapid events through a
/// tokio mpsc with a short settle delay.
pub fn start(app: AppHandle, path: PathBuf) {
    let (tx, mut rx) = tokio::sync::mpsc::channel::<()>(8);

    // The notify watcher runs on its own thread; forward relevant events into tx.
    let mut watcher = match RecommendedWatcher::new(
        move |res: notify::Result<notify::Event>| {
            if let Ok(ev) = res {
                if matches!(ev.kind, EventKind::Modify(_) | EventKind::Create(_) | EventKind::Remove(_)) {
                    let _ = tx.blocking_send(());
                }
            }
        },
        notify::Config::default(),
    ) {
        Ok(w) => w,
        Err(_) => return, // watching is best-effort; poll still covers us
    };

    // Watch the parent dir (editors often replace the file via rename, which
    // a direct file watch misses).
    if let Some(parent) = path.parent() {
        let _ = watcher.watch(parent, RecursiveMode::NonRecursive);
    }

    tokio::spawn(async move {
        // Keep the watcher alive for the task's lifetime.
        let _keep = watcher;
        let want = path;
        while rx.recv().await.is_some() {
            // Settle: drain any burst, wait briefly, then act once.
            tokio::time::sleep(Duration::from_millis(150)).await;
            while rx.try_recv().is_ok() {}
            // Only react to events touching our file (parent-dir watch is broad).
            // We can't cheaply know which file changed after coalescing, so just
            // re-query unconditionally — cheap, and correctness over precision.
            let _ = want; // (path retained for clarity / future filtering)
            if let Ok(rows) = cli::run_json::<Vec<ProjectStatus>>(&["ps", "--json"]).await {
                let _ = app.emit("projects://updated", &rows);
            }
        }
    });
}
