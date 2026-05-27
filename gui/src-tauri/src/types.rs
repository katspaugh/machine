use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ProjectStatus {
    pub name: String,
    pub status: String,
    #[serde(default)]
    pub uptime_seconds: Option<u64>,
    #[serde(default)]
    pub cpu_percent: Option<f64>,
    #[serde(default)]
    pub mem_used_bytes: Option<u64>,
    #[serde(default)]
    pub mem_total_bytes: Option<u64>,
    #[serde(default)]
    pub primary_repo: Option<String>,
    #[serde(default)]
    pub branch: Option<String>,
    #[serde(default)]
    pub idle_seconds: Option<u64>,
    #[serde(default)]
    pub ports: Vec<u16>,
    #[serde(default)]
    pub profiles: Vec<String>,
    #[serde(default)]
    pub repos: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ProjectConfig {
    pub name: String,
    #[serde(default)]
    pub repos: Vec<String>,
    #[serde(default)]
    pub primary_repo: Option<String>,
    #[serde(default)]
    pub profiles: Vec<String>,
    #[serde(default)]
    pub shell: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DoctorCheck {
    pub name: String,
    pub status: String,
    #[serde(default)]
    pub detail: Option<String>,
    #[serde(default)]
    pub hint: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DoctorSummary {
    pub checks: u32,
    pub fails: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DoctorReport {
    pub checks: Vec<DoctorCheck>,
    pub summary: DoctorSummary,
}

#[cfg(test)]
mod tests {
    use super::*;

    // Fixture copied from real `machine ps --json` output (one running, one stopped).
    const PS_JSON: &str = r#"[
      {"name":"wallet","status":"Running","uptime_seconds":8040,"cpu_percent":2.1,
       "mem_used_bytes":1932735283,"mem_total_bytes":8589934592,"primary_repo":"wallet",
       "branch":"main","idle_seconds":180,"ports":[3000,5173],
       "profiles":["cypress"],"repos":["git@github.com:you/wallet.git"]},
      {"name":"blog","status":"Stopped","uptime_seconds":null,"cpu_percent":null,
       "mem_used_bytes":null,"mem_total_bytes":null,"primary_repo":"blog","branch":null,
       "idle_seconds":null,"ports":[],"profiles":["cypress"],
       "repos":["git@github.com:you/blog.git"]}
    ]"#;

    #[test]
    fn parses_ps_json() {
        let rows: Vec<ProjectStatus> = serde_json::from_str(PS_JSON).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].name, "wallet");
        assert_eq!(rows[0].status, "Running");
        assert_eq!(rows[0].uptime_seconds, Some(8040));
        assert_eq!(rows[0].ports, vec![3000, 5173]);
        assert_eq!(rows[1].status, "Stopped");
        assert_eq!(rows[1].uptime_seconds, None);
        assert_eq!(rows[1].cpu_percent, None);
        assert!(rows[1].ports.is_empty());
    }

    #[test]
    fn parses_list_json() {
        let s = r#"[{"name":"blog","repos":["git@github.com:you/blog.git"],
          "primary_repo":"blog","profiles":["cypress"],"shell":null}]"#;
        let rows: Vec<ProjectConfig> = serde_json::from_str(s).unwrap();
        assert_eq!(rows[0].name, "blog");
        assert_eq!(rows[0].shell, None);
        assert_eq!(rows[0].profiles, vec!["cypress"]);
    }

    #[test]
    fn parses_doctor_json() {
        let s = r#"{"checks":[
          {"name":"limactl on PATH","status":"ok","detail":null,"hint":null},
          {"name":"SSH_AUTH_SOCK unset","status":"fail","detail":null,
           "hint":"start your SSH agent"}],
          "summary":{"checks":2,"fails":1}}"#;
        let report: DoctorReport = serde_json::from_str(s).unwrap();
        assert_eq!(report.checks.len(), 2);
        assert_eq!(report.summary.fails, 1);
        assert_eq!(report.checks[1].hint.as_deref(), Some("start your SSH agent"));
    }

    #[test]
    fn tolerates_unknown_status_string() {
        let s = r#"[{"name":"x","status":"Broken","ports":[],"profiles":[],"repos":[]}]"#;
        let rows: Vec<ProjectStatus> = serde_json::from_str(s).unwrap();
        assert_eq!(rows[0].status, "Broken"); // free-form string, never panics
    }
}
