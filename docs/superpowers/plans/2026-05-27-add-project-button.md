# Add "Add project" Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface an always-available "Add project" button in the sidebar footer that opens the existing project-creation modal (with profile selection), regardless of how many projects exist.

**Architecture:** Reuse the existing `FirstRunModal` (name + repo + profile chips) and `add_project` Tauri command. Generalize the modal's wording via a `firstRun` prop, add an `onAdd` button to `Sidebar`, and wire it through `+page.svelte` to the same submit handler the empty state already uses. No backend changes.

**Tech Stack:** SvelteKit (Svelte 5 runes), TypeScript, Vitest + @testing-library/svelte. All commands run from `gui/`.

---

### Task 1: Generalize FirstRunModal wording

**Files:**
- Modify: `gui/src/lib/components/FirstRunModal.svelte`
- Test: `gui/src/lib/components/FirstRunModal.test.ts`

- [ ] **Step 1: Write the failing test**

Add this test inside the existing `describe("FirstRunModal", ...)` block in `gui/src/lib/components/FirstRunModal.test.ts`:

```ts
  it("uses add-another wording when firstRun is false", () => {
    const { getByRole } = render(FirstRunModal, {
      props: { profiles: [], firstRun: false, onSubmit: () => {}, onSkip: () => {} },
    });
    expect(getByRole("heading", { name: "Add project" })).toBeTruthy();
    expect(getByRole("button", { name: /cancel/i })).toBeTruthy();
  });

  it("defaults to first-run wording", () => {
    const { getByRole } = render(FirstRunModal, {
      props: { profiles: [], onSubmit: () => {}, onSkip: () => {} },
    });
    expect(getByRole("heading", { name: /add your first project/i })).toBeTruthy();
    expect(getByRole("button", { name: /skip/i })).toBeTruthy();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- FirstRunModal`
Expected: FAIL — the "Add project" heading / "Cancel" button are not found (modal still hard-codes first-run wording).

- [ ] **Step 3: Add the `firstRun` prop and conditional wording**

In `gui/src/lib/components/FirstRunModal.svelte`, change the props destructure to add `firstRun` (default `true`):

```ts
  let { profiles, firstRun = true, onSubmit, onSkip }: {
    profiles: string[];
    firstRun?: boolean;
    onSubmit: (p: { name: string; repo: string; profiles: string[] }) => void;
    onSkip: () => void;
  } = $props();
```

Change the heading line from:

```svelte
    <h2>Add your first project</h2>
```

to:

```svelte
    <h2>{firstRun ? "Add your first project" : "Add project"}</h2>
```

Change the secondary button line from:

```svelte
      <button onclick={onSkip}>Skip</button>
```

to:

```svelte
      <button onclick={onSkip}>{firstRun ? "Skip" : "Cancel"}</button>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm test -- FirstRunModal`
Expected: PASS — all FirstRunModal tests (existing + 2 new) green.

- [ ] **Step 5: Commit**

```bash
git add gui/src/lib/components/FirstRunModal.svelte gui/src/lib/components/FirstRunModal.test.ts
git commit -m "Generalize FirstRunModal wording with firstRun prop"
```

---

### Task 2: Add the sidebar "Add project" button

**Files:**
- Modify: `gui/src/lib/components/Sidebar.svelte`
- Test: `gui/src/lib/components/Sidebar.test.ts`

- [ ] **Step 1: Write the failing test**

Add this test inside the existing `describe("Sidebar", ...)` block in `gui/src/lib/components/Sidebar.test.ts`:

```ts
  it("fires onAdd when the add button is clicked", async () => {
    const onAdd = vi.fn();
    const { getByRole } = render(Sidebar, {
      props: { projects: [p("wallet", "Running")], jobs: new Map(),
        selectedName: "wallet", onSelect: () => {}, onAdd },
    });
    await fireEvent.click(getByRole("button", { name: /add project/i }));
    expect(onAdd).toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- Sidebar`
Expected: FAIL — no button matching `/add project/i` exists yet.

- [ ] **Step 3: Add the `onAdd` prop and footer button**

In `gui/src/lib/components/Sidebar.svelte`, change the props destructure from:

```ts
  let { projects, jobs, selectedName, onSelect }: {
    projects: ProjectStatus[];
    jobs: Map<JobId, JobState>;
    selectedName: string | null;
    onSelect: (name: string) => void;
  } = $props();
```

to:

```ts
  let { projects, jobs, selectedName, onSelect, onAdd }: {
    projects: ProjectStatus[];
    jobs: Map<JobId, JobState>;
    selectedName: string | null;
    onSelect: (name: string) => void;
    onAdd: () => void;
  } = $props();
```

In the same file, add the footer button just before the closing `</nav>` tag (after the `{/each}` block):

```svelte
    <button class="add" onclick={onAdd}>+ Add project</button>
```

Update the `.sidebar` style rule to lay the nav out as a flex column so the button sits at the bottom, and add `.add` button styles. Change:

```css
  .sidebar { width: 180px; border-right: 1px solid var(--border);
    background: var(--sidebar-bg); padding: 8px 0; }
```

to:

```css
  .sidebar { width: 180px; border-right: 1px solid var(--border);
    background: var(--sidebar-bg); padding: 8px 0;
    display: flex; flex-direction: column; }
  .add { margin: auto 8px 4px; padding: 6px 12px; border: 1px dashed var(--border);
    border-radius: 6px; background: none; cursor: pointer; font-size: 12px;
    color: var(--muted); text-align: left; }
  .add:hover { color: var(--text); border-color: var(--accent); }
```

(The `margin-top: auto` via the `auto` in the `.add` shorthand pushes the button to the footer.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm test -- Sidebar`
Expected: PASS — all Sidebar tests (existing + new) green.

- [ ] **Step 5: Commit**

```bash
git add gui/src/lib/components/Sidebar.svelte gui/src/lib/components/Sidebar.test.ts
git commit -m "Add Add project button to sidebar footer"
```

---

### Task 3: Wire the button through the page

**Files:**
- Modify: `gui/src/routes/+page.svelte`

This task has no unit test of its own (the page is integration glue verified by `pnpm check` and the running app); the behavior is covered by Task 1 and Task 2 component tests.

- [ ] **Step 1: Rename the `firstRun` state flag to `showAddModal`**

In `gui/src/routes/+page.svelte`, change:

```ts
  let firstRun = $state(false);
```

to:

```ts
  let showAddModal = $state(false);
```

- [ ] **Step 2: Update the onMount empty-projects branch**

Change:

```ts
      if ($projects.length === 0) firstRun = true;
```

to:

```ts
      if ($projects.length === 0) showAddModal = true;
```

- [ ] **Step 3: Update the submit handler to use the renamed flag**

In `firstRunSubmit`, change the success line from:

```ts
      firstRun = false;
```

to:

```ts
      showAddModal = false;
```

- [ ] **Step 4: Pass `onAdd` to the Sidebar**

Change the `<Sidebar ... />` usage from:

```svelte
  <Sidebar projects={$projects} jobs={$jobs} selectedName={$selectedName}
    onSelect={(n) => ($selectedName = n)} />
```

to:

```svelte
  <Sidebar projects={$projects} jobs={$jobs} selectedName={$selectedName}
    onSelect={(n) => ($selectedName = n)} onAdd={() => (showAddModal = true)} />
```

- [ ] **Step 5: Update the EmptyState and modal usage**

Change the EmptyState usage from:

```svelte
    <EmptyState onAdd={() => (firstRun = true)} />
```

to:

```svelte
    <EmptyState onAdd={() => (showAddModal = true)} />
```

Change the modal block from:

```svelte
{#if firstRun}
  <FirstRunModal profiles={availableProfiles}
    onSubmit={firstRunSubmit} onSkip={() => (firstRun = false)} />
{/if}
```

to:

```svelte
{#if showAddModal}
  <FirstRunModal profiles={availableProfiles} firstRun={$projects.length === 0}
    onSubmit={firstRunSubmit} onSkip={() => (showAddModal = false)} />
{/if}
```

- [ ] **Step 6: Typecheck the project**

Run: `pnpm check`
Expected: 0 errors (the pre-existing `tsconfig.json` base-config warning from `.svelte-kit` is unrelated and acceptable).

- [ ] **Step 7: Run the full test suite**

Run: `pnpm test`
Expected: PASS — all component tests green.

- [ ] **Step 8: Commit**

```bash
git add gui/src/routes/+page.svelte
git commit -m "Wire Add project button through the page"
```

---

### Task 4: Manual verification in the running app

**Files:** none (manual check).

- [ ] **Step 1: Launch the app**

From `gui/`, with `~/.cargo/bin` on PATH and the command sandbox disabled (Vite binds `localhost:1420`):

Run: `pnpm tauri dev`
Expected: the desktop window opens and the project list renders.

- [ ] **Step 2: Verify the button and modal**

With at least one project present, confirm a `+ Add project` button shows at the sidebar footer. Click it; confirm the modal opens titled "Add project" with a "Cancel" button and the profile chips. Enter a name + repo, toggle a profile, click Create; confirm the new project appears in the sidebar and is selected.

- [ ] **Step 3: Verify first-run wording still works**

(Optional, if a zero-project state is reachable) Confirm that with no projects the modal still reads "Add your first project" with a "Skip" button.
