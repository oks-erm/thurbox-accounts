# Simple Session Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Named accounts in normal Ctrl+N, with safe inline switching and no terminal setup.

**Architecture:** Add owned per-profile agent entries and a narrow checked adapter to the normal Lua creation picker. Supervise named sessions from their first turn using the existing guard engine, initially with one account and no cross-account proof. An inline chooser previews a frozen source/target plan; confirmation safely pauses the guarded source, enrolls or extends selected history, and resumes the same native UUID through Shared.

**Tech Stack:** Python 3.11 standard library, Lua, public Thurbox CLI, local tmux.

**Spec:** docs/superpowers/specs/2026-10-30-simple-session-accounts-design.md

## Global Constraints

- Standalone thurbox-accounts repo; local WSL/tmux plus Mac development checks.
- No dependency, credential copying, policy/trust edits or implicit model checks.
- Explicit source/target organization approval before cross-account history access.
- Named sessions supervised from first turn; unknown work refuses switching.
- Preserve custom panes, layouts, libraries and agent registry entries.
- Codex remains default; no remote routing or automatic rotation.

## Review Focus

- Registry reloads and partial registration: new accounts appear without rewriting custom agents.
- Restarted/stale session rows: immutable UUID/profile/owner must match before launch or switch.
- Slow auth/verification and source changes: confirmation freezes owner/account identities and rechecks before stopping.
- Idle-parent races and background jobs: freeze/recheck before shutdown, never infer completion from terminal text.
- Small screens/cancel/changed selection: never submit a hidden or stale sharing approval.

### Task 1: Named guarded sessions

**Files:** create thurbox_accounts/simple.py, tests/test_simple.py; modify agent_install.py, guard.py, shared.py, desktop.py, pane.py, cli.py, manifest.

**Interfaces:** `Simple.bootstrap(profile, native_args, owner, cwd)` creates/validates a single-account guard record and immutable binding; `Simple.source(session)` returns stopped row/binding/path/digest for safe enrollment. `register_profiles(service, launcher)` additively registers owned `Claude — LABEL` choices. Guard launcher dispatches its own account options before normal native arguments.

- [ ] Add failing tests for named-agent ownership/idempotence/custom edits; bootstrap no proof, changed UUID/profile and stale owner refusals.
- [ ] Implement registration/dispatch and single-account record validation. Wait for persisted Thurbox row before verifying startup. Preserve hook-only native settings and directories.
- [ ] Reuse lifetime writer/supervisor; ordinary starts never grant cross-account access. Test actual synthetic process startup, refusal on working/background state and safe idle stop.
- [ ] Run targeted unit/compile and synthetic tmux creation tests; commit.

### Task 2: Frozen inline switch workflow

**Files:** simple.py, shared.py, guard.py, cli.py, pane.py; tests/test_simple.py, tests/test_shared.py; examples/shared_smoke.py.

**Interfaces:** `Simple.preview(session, target)` returns single-use five-minute source/target consent plan and proof readiness. `Simple.confirm(token, consent=True)` revalidates identities/owner, safely stops, enrolls/extends approved aliases and launches selected target. `simple-preview`, `simple-confirm` expose those methods; `pane-run` supplies friendly TSV receipts.

- [ ] Write failing tests for no consent, expired/reused plan, missing proof, changed identities/owner, target already exists, mode Off and failed recovery evidence.
- [ ] Implement guarded idle/quota pause using existing control channel and freeze/recheck; target preflight precedes pause. Keep legacy quota-only switch behavior unless explicit inline action chooses idle-safe policy.
- [ ] Enroll a stopped single source using existing move/link path after revalidation; extend approved groups with durable records and collision checks; launch exact target rather than cycle order. Maintain confirmed-account evidence.
- [ ] Test real synthetic A→B→A with same UUID/history, no fork/model calls, busy source PID survives, stale source cannot restart. Commit.

### Task 3: Normal creation and inline UI

**Files:** accounts_ui.py, new UI adapter/helper, ui/account_status.lua, ui/accounts.lua, install.py, CLI registration; UI/install tests and real TUI smoke.

**Interfaces:** owned generated adapter cleans registry account labels in normal Ctrl+N, hides internal guard choice, retains default/provider/project/worktree choices. `account-status` adds `Switch account` hit target; a compact modal performs preview, optional paid verification review, sharing confirmation, errors/progress/recovery. F7 is only account management.

- [ ] Add failing installer tests for recognized upstream creation template, owned updates, custom edits, symlinks, fresh install/rerun, complete destination preflight and package payload.
- [ ] Implement minimal checked picker integration and named registry refresh on explicit account add/status. Do not mutate render snapshots or grant capabilities.
- [ ] Implement inline modal using supported nodes/actions, keyboard/clicks, cancellation, stale-selection rejection and height-gated consent. Explain unguarded sources; no misleading switch action.
- [ ] Validate actual Ctrl+N and inline chooser in isolated real TUI with synthetic backend; preserve existing guided-pane and strip smoke tests. Commit.

### Task 4: Delivery

**Files:** README.md, docs/ACCOUNTS.md, docs/VALIDATION.md, AGENTS.md, versions/manifest.

- [ ] Replace colleague-facing instructions with sign-in once, Ctrl+N choose account, inline Switch account; clearly describe permission and optional paid verification.
- [ ] Run full Python suite/compile, distribution, real TUI and synthetic tmux smoke, fresh installer/rerun and live plugin check.
- [ ] Request a fresh whole-branch review, resolve findings with regression tests, and rerun affected checks.
- [ ] Commit, fast-forward main, push; verify remote hash and CI status. Report real WSL/Enterprise verification limits.
