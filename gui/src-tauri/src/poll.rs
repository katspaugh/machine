use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;
use tauri::{AppHandle, Emitter};

use crate::cli;
use crate::types::ProjectStatus;

pub struct Focus(pub AtomicBool);
impl Default for Focus {
    fn default() -> Self { Focus(AtomicBool::new(true)) }
}

const FOCUSED: Duration = Duration::from_secs(2);
const BLURRED: Duration = Duration::from_secs(30);

/// Poll `machine ps --json` forever, emitting `projects://updated` with the
/// full Vec whenever it changes. Interval depends on window focus.
pub fn start(app: AppHandle, focus: Arc<Focus>) {
    tokio::spawn(async move {
        let mut last: Option<Vec<ProjectStatus>> = None;
        loop {
            match cli::run_json::<Vec<ProjectStatus>>(&["ps", "--json"]).await {
                Ok(rows) => {
                    if last.as_ref() != Some(&rows) {
                        let _ = app.emit("projects://updated", &rows);
                        last = Some(rows);
                    }
                }
                Err(_) => { /* transient; try again next tick */ }
            }
            let dur = if focus.0.load(Ordering::Relaxed) { FOCUSED } else { BLURRED };
            tokio::time::sleep(dur).await;
        }
    });
}
