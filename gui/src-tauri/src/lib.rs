mod cli;
mod types;

use types::{DoctorReport, ProjectConfig, ProjectStatus};

#[tauri::command]
async fn list_projects() -> Result<Vec<ProjectStatus>, cli::CliError> {
    cli::run_json(&["ps", "--json"]).await
}

#[tauri::command]
async fn list_config() -> Result<Vec<ProjectConfig>, cli::CliError> {
    cli::run_json(&["list", "--json"]).await
}

#[tauri::command]
async fn run_doctor() -> Result<DoctorReport, cli::CliError> {
    // doctor exits 1 when checks fail, but still prints valid JSON. run_json
    // treats non-zero as an error, so use run_json_any_exit which accepts any
    // exit code as long as the JSON parses.
    cli::run_json_any_exit(&["doctor", "--json"]).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            list_projects,
            list_config,
            run_doctor
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
