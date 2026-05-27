# Add "Add project" button with profile selection

**Date:** 2026-05-27
**Component:** `gui/` (Tauri + SvelteKit desktop app)

## Problem

The GUI can already create a project via `FirstRunModal` (name + repo +
profile-chip selection) backed by the `add_project` Tauri command. But that
modal is only reachable from the empty state (zero projects) or first run.
Once at least one project exists, there is no UI to add another — the user must
edit `projects.toml` by hand.

## Goal

Surface an always-available "Add project" button that opens the existing
project-creation modal (profile selection included), regardless of how many
projects exist.

## Design

### 1. `Sidebar.svelte`

- Add an `onAdd: () => void` prop.
- Render a `+ Add project` button pinned to the bottom of the sidebar, below
  the project list.
- Make `.sidebar` a flex column so the list grows and the button stays at the
  footer.

### 2. `FirstRunModal.svelte` (generalize in place)

The modal is currently hard-coded for first-run wording. Add context:

- New prop `firstRun: boolean` (default `true`).
- Heading: `firstRun ? "Add your first project" : "Add project"`.
- Secondary button label: `firstRun ? "Skip" : "Cancel"`.
- Everything else (name validation, repo input, profile chips, submit) is
  unchanged.

Keep the filename `FirstRunModal.svelte` to avoid churn; it now serves both the
first-run and add-another cases.

### 3. `+page.svelte`

- Rename the `firstRun` state flag to `showAddModal` for clarity (it no longer
  means strictly "first run").
- Pass `onAdd={() => (showAddModal = true)}` to `Sidebar`.
- Keep the empty-state `onAdd` wired to the same flag.
- Render the modal with `firstRun={$projects.length === 0}` so wording adapts.
- Reuse the existing `firstRunSubmit` handler unchanged — it already calls
  `api.addProject`, reloads the project list, selects the new project, and
  closes the modal.

### No backend changes

`add_project(name, repo, profiles)` and `list_profiles()` already exist and
provide exactly what the modal needs.

## Data flow

```
click "+ Add project"  ->  showAddModal = true
modal opens (availableProfiles already loaded onMount)
user enters name + repo, toggles profile chips
submit  ->  api.addProject(name, repo, profiles)
        ->  $projects = await api.listProjects()
        ->  $selectedName = name
        ->  showAddModal = false
```

## Error handling

Unchanged: `firstRunSubmit` wraps `addProject` in try/catch and sets the
existing `error` bar on failure. Modal stays open implicitly because the
failure path does not flip `showAddModal`.

## Testing

- `Sidebar.test.ts`: clicking the add button fires the `onAdd` callback.
- `FirstRunModal.test.ts`: with `firstRun={false}`, heading reads "Add project"
  and the secondary button reads "Cancel"; default still reads first-run
  wording.
- Existing modal submit/validation tests continue to pass.
