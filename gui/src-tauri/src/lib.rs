mod cli;
mod jobs;
mod types;

use std::sync::Arc;
use jobs::{JobId, JobRegistry};
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

#[tauri::command]
async fn add_project(
    name: String,
    repo: String,
    profiles: Vec<String>,
) -> Result<(), cli::CliError> {
    let mut args: Vec<String> = vec![
        "config".into(), "add-project".into(), name,
        "--repo".into(), repo,
    ];
    for p in &profiles {
        args.push("--profile".into());
        args.push(p.clone());
    }
    let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
    cli::run_ok(&arg_refs).await
}

#[tauri::command]
async fn spawn_lifecycle(
    app: tauri::AppHandle,
    registry: tauri::State<'_, Arc<JobRegistry>>,
    project: String,
    action: String,
) -> Result<JobId, jobs::JobError> {
    jobs::spawn_lifecycle(app, registry.inner().clone(), project, action).await
}

#[tauri::command]
async fn cancel_job(
    registry: tauri::State<'_, Arc<JobRegistry>>,
    job_id: JobId,
) -> Result<(), ()> {
    jobs::cancel_job(registry.inner().clone(), job_id).await;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(Arc::new(JobRegistry::default()))
        .invoke_handler(tauri::generate_handler![
            list_projects,
            list_config,
            run_doctor,
            add_project,
            spawn_lifecycle,
            cancel_job
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
