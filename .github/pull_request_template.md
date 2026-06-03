**What changed**

**How it was verified**

- [ ] `bash tests/lint.sh` + `bash tests/unit.sh` green
- [ ] VM smokes run, if the change touches templates/provision (`bash tests/run-all.sh <p>`)
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` (if user-visible)
