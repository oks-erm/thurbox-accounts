# Current-conversation switching mode implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, test-first, with one independent final review.

**Goal:** Enable/disable one-click account switching for the current ordinary WSL Claude conversation.
**Architecture:** A mode service verifies source provenance and issues expiring confirmation plans, snapshots only selected stopped history, then reuses Shared supervision. Lua projects the currently selected session and explicit setup/mode controls. CLI switches enforce Off.
**Tech Stack:** Existing Python 3.11 standard library, Lua, public Thurbox CLI, tmux.
**Spec:** ../specs/2026-10-29-conversation-switching-mode-design.md

## Global constraints

WSL/local tmux only. No new dependencies or credentials access/copy. Read-only refresh. Explicit account/context consent and separately approved paid compatibility checks. Preserve original untracked history; same UUID and canonical history after enrollment. No automatic rotation. Off blocks cross-account launch without killing current writer. Preserve legacy behavior. No real auth/model calls in synthetic tests.

## Review focus

- Identity inferred from picker instead of native source directory/launch metadata must fail.
- Source changes or starts after preview, unsafe sidecars, and target collisions must preserve original files.
- Off racing a switch or failed-transition recovery must not launch an unapproved account.
- Current ordinary conversation must be visible without existing bindings; stale selection must not act on another conversation.
- Small-pane confirmation must expose all identities and context/allowance notices before action.

## Task 1: Verified adoption and mode policy

Files: new mode.py and tests/test_mode.py; shared.py and desktop.py integration.
Interfaces: Mode.preview(session, profiles), Mode.enable(token,consent), Mode.set_enabled(session, enabled).
- [ ] Write failing tests for stopped untracked source adoption, no auth on read projection, wrong identities/source mutation/sidecar links/collisions, Off/On and recovery gates.
- [ ] Run targeted tests (Expected: failures for absent mode).
- [ ] Implement bounded source verification, confirmation and recovery records, safe initial snapshot and selected aliases; retain existing Shared launch guards.
- [ ] Run targeted tests (Expected: pass), commit focused backend change.

## Task 2: Current-session controls and CLI

Files: cli.py, pane.py, ui/accounts.lua, extension.toml, tests/test_pane.py; examples/guided_pane_smoke.py.
Interfaces: pane-state --session returns source metadata without auth; mode-preview emits encoded immutable plan for UI confirmation; mode-enable token; mode-on/off current managed session.
- [ ] Add failing projection/CLI and real Lua smoke assertions.
- [ ] Implement current-session display, separate login selection, review accounts, paid verify and prepare flow, On/Off, named switch/recovery status.
- [ ] Preserve backend frozen confirmation tokens and height guards; small-window check.
- [ ] Run unit and isolated UI checks (Expected: pass); commit focused pane change.

## Task 3: Integration, docs, review and delivery

Files: examples/shared_smoke.py mode option, README.md, docs/ACCOUNTS.md, AGENTS.md, validation notes.
- [ ] Extend real tmux synthetic smoke with ordinary source adoption, original preservation, mode-off refusal, re-enable, A/B/A same-UUID switches and distinct native environments.
- [ ] Run full tests/compile/diff checks; installer validation, isolated VM/PTY and real tmux smoke (Expected: pass).
- [ ] Independent final review, fix important findings test-first, rerun relevant checks.
- [ ] Install live checked pane on connected Mac, commit/push, inspect GitHub CI. Report WSL/native-auth verification limits.

## Ledger

Base: df9369b. Approved design and implement/test/push request in current chat.

Task 1 complete: 13 mode tests and 72 full-suite tests passed. New tests first
failed because mode was absent. Adopted originals remain unchanged; tracked
sources reuse existing safe move/link enrollment. No policy gate removed.
Ruling: use nested repository git worktree fallback because app-managed worktrees
attach to the enclosing engineering-tools repository, not this standalone repo.
Ruling: an ordinary source must be explicitly stopped first; no safe evidence
exists to automatically terminate pre-mode background tools. Cost: one safe stop
is required during initial setup. The pane explains this directly.

Task 2 complete: current source projection, frozen backend confirmation receipt,
separate login selection, mode On/Off and recovery labels implemented. 15 mode
tests and 7 pane tests pass. Real Lua/PTY smoke passes ordinary setup, missing
proof refusal, ordered identities/confirmation, Off action refusal, On and named
switch, F7 login return, 80x20 controls and short-pane consent blocking.
Task 3 integration evidence: real Thurbox/tmux ordinary adoption + Off/On + A/B/A
+ same UUID/history/profile isolation + desktop/stale-writer checks pass at
/private/tmp/tbx-shared-smoke-8cdcwbv4. All native commands are synthetic fixtures.

Pre-review checks: full suite 77/77, compileall and diff check pass. Real UI
Off/On/named switch and short-window checks passed at tbx-guided-6f27kzm4.
No outstanding plan/interface conflicts. Final review and live delivery remain.

Final review: three Important issues confirmed and fixed test-first in one pass:
full tracked-source manifest/stopped recheck before moves; prepared-source final
check after slow launch preflights; stale/unresolved Lua current-session selection
fails closed. New regression tests reproduced all three before fixes.
Also fixed pre-existing async Bash completion gap required by mode safety:
PostToolUse does not discharge background work; structured completion/Stop registry
can discharge known tasks. Unknown completion stays blocked. Native hook reference
consulted; actual Enterprise auth/model requests remain untested.
Consent wording now distinguishes untracked snapshots from tracked move/link history.
No deferred review findings.

Final fixes verified: 82/82 Python tests, compileall/diff check, real Lua selection
regressions and tmux hook-bridge background refusal plus A/B/A all pass.
No remaining review findings. Live installation, push and CI inspection pending.
