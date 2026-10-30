# Working on Thurbox Accounts

## Purpose and architecture

This standalone extension does only Claude Enterprise account switching: isolated
native SSO profiles, account-scoped new Thurbox sessions and confirmed conversation
handoff. Do not add debate, code generation or adversarial workflows here.
Python 3.11+ standard library, Lua pane, no runtime third-party dependencies.
`accounts.py` owns profile metadata/native auth/handoff; `cli.py` parses account
actions; `accounts_ui.py` safely delivers `ui/accounts.lua`; `core.py` owns atomic
private files and redaction; `runtime.py` bounds argv subprocesses; `thurbox.py`
is the public JSON CLI transport. No database, migrations, network SDK or deployment.

## Commands

```sh
./bin/thurbox-accounts --help
python3.11 -m unittest discover -s tests -q
python3.11 -m compileall -q thurbox_accounts tests examples
python3.11 examples/live_smoke.py --thurbox-cli /path/to/thurbox-cli
```

No third-party lint/type checker configured. Optional pip builds use setuptools.
The extension manifest must include every runtime module and Lua resource. Package
data must include the Lua template for pip installs. Keep installation docs brief.

## Data and integration contracts

Default private state remains ~/.local/share/thurbox-loop/accounts to preserve
users of the former combined extension; --accounts-dir overrides it. Profiles,
bindings, confirmation plans, recovery operations and UI delivery hashes are JSON.
Native Claude owns credentials. Only CLAUDE_CONFIG_DIR is account-scoped; check
conflicting auth/provider variables in caller and actual tmux environment.
Use public Thurbox version metadata to locate its socket, and enumerate sessions.
Handoff requires a stopped source, pinned target identity, single-use five-minute
plan and compatibility proof for the exact native Claude binary. Fork through
native Claude once, then create Thurbox with --resume UUID. Never persist snapshot
resume/fork agent arguments: they would replay context on every restart.
The source remains stopped and unchanged. Persist recovery UUID before native fork.

## Safety and validation

Never read/copy credentials, grant UI capabilities, trust hooks/folders, weaken
managed policy, delete user state, force-push or deploy without explicit authority.
Preview cannot send context. Transfer only after source/target-specific confirmation.
Preserve custom UI edits and user layout; run plugin check after live pane edits.
Profiles keep the old data path intentionally; do not auto-migrate or rename it.
Run account/unit/distribution suites and compile checks before commit, real tmux
smoke after transport changes, and inspect CI after push. Smoke uses synthetic
auth; do not claim Enterprise SSO or actual cross-organization transfer passed.

## Installation regression

Thurbox 2.75.2 advertises git+ extension installation but fetches its manifest
through an unsupported Git source path; it fails before cloning. Do not put that
command back into README. `install.py` orchestrates local-directory installation,
interface materialization, checked pane delivery and non-overwriting command
linking. Its `install` action runs from a cloned checkout; no TUI or login needed.
Validate the exact README clone/install flow in a clean isolated profile and
rerun it, not only a local extension install in an existing configured profile.

## Shared conversations (0.2.0)

`shared.py` owns selected canonical history/aliases and serialized transitions;
`guard.py` owns native hooks and process-lifetime writer locking. `shared_probe.py`
is an opt-in paid synthetic native proof; never generate a real proof from fake
accounts/tests. `agent_install.py` additively registers an absolute
`claude-accounts` agent and backs up agents.toml; default Claude is unchanged.
Only selected UUID transcript + UUID sidecar directory are linked, never entire
config/project directories. Keep managed identity/order/build proof checks,
durable owner reservation, unknown-state refusals and orphan evidence.
No model request/fork on switch. Stop is safe only for confirmed native quota
state with no workers, or an explicitly stopped source with no pending workers.
Never clear a stale native_pid/starting record merely because its writer lock is
free: an orphan may survive. Preserve replaced aliases for manual recovery.
`examples/shared_smoke.py` exercises real tmux A→B→A with synthetic Claude and no
API calls. Run it after shared transport/supervisor changes, then unit/compile
checks, live plugin check and installer rerun. No CI workflow or deployment exists.

## Mac desktop companion (0.3.0)

`desktop.py` is a narrow owned-session adapter. `desktop/Accounts.swift` provides
a dependency-free SwiftUI/AppKit window (macOS 13+). `desktop_install.py` builds
and ad-hoc signs an owned app bundle under ~/Applications, keeping update backups.
`thurbox-accounts desktop-install` requires the checkout or installed extension
payload and Apple command-line tools; a bare Python wheel lacks the Swift source.
App/backend configuration contains executable paths only. Never import browser
cookies, login databases or native credential files. Native SSO uses a private
Terminal command file; model requests require Send or confirmed verification.

Refresh must stay read-only and off the UI thread. Drafts are per conversation.
Reject enrolled originals and stale/foreign sessions on every input/resume path.
Hold transition-UUID across resume preflights; use Shared._launch reservation for
shared resume. Do not introduce an alternate authentication or writer policy.
The hidden --desktop-deadline cooperatively raises through runtime.execute to
clean its subprocess group before returning; uncertain outer shutdown disables
UI mutations. Unknown send receipts must not become a silent success or retry.

Validation: full Python suite/compile, desktop-install fresh/rerun/collision tests,
`examples/shared_smoke.py --desktop`, codesign --verify --deep --strict, compiled
app `--bridge-check` and `--ui-model-check`, then native window inspection.
Do not certify real SSO or native quota portability from synthetic fixtures.

## Guided pane

`pane.py` supplies a percent-encoded read model and friendly receipts; mutations
reuse CLI/Accounts/Shared policy. Refresh must never authenticate or send requests.
Friendly names derive internal IDs; preserve explicit labels and unique names.
Lua controls support clicks and Tab/Enter, with F7 returning from native login.
Sharing confirmation freezes source/account order and is disabled unless all
consent text fits. Keep new-conversation form separate from the session list.
`examples/guided_pane_smoke.py` exercises the real isolated Lua VM/TUI with
stubbed operations, no trusted capabilities, logins or model requests.
Thurbox 2.75.2 emits a generic raw-on_click catalog warning even when semantic
commands exist; do not remove mouse support just to hide that warning.
Windows use requires WSL; native PowerShell is not supported.

## Current-conversation mode (0.4.0)

`mode.py` verifies source launch metadata/native auth and bounds the selected
transcript/sidecars (20 MB per file, 100 MB total, 2000 entries). Preview issues a
single-use five-minute plan frozen to source metadata/content and approved group.
No implicit paid verification; no auto-stop of untracked sources. Adoption keeps
original untracked files, snapshots only selected UUID data, then reuses Shared
writer/reservation/proof guards. Tracked sources reuse the existing move/link path.
Persist recovery records before writing and refuse collisions/unsafe paths.
Mode changes hold the same transition lock as switches. Off rejects Shared.switch
and cross-account recovery/resume; same-account resume remains allowed. Failed
launches display the last confirmed account. Legacy records remain manual.
`pane-state --session` exposes the selected ordinary session without auth or
mutations, maps old originals to their current managed owner, and explains
unsupported agents. Keep login/new-work selection distinct from active account.
Validate `examples/shared_smoke.py --mode --desktop` plus the real Lua smoke.

Revalidate the complete frozen mode source under the transition lock immediately
before tracked history moves. Revalidate prepared canonical content and original
stopped metadata after slow launch checks and recovery listing, before reservation.
Explicit pane selection expires when store.selected changes; unresolved current
owners must not fall back to unrelated conversations.
Track asynchronous Bash jobs past PostToolUse. Only exact structured task completion
or the main native Stop registry snapshot can discharge them; missing/unknown
completion remains a blocker for switching and recovery. Never clear this evidence
because the parent stopped or the account hit quota. The optional Stop task registry
is documented at https://code.claude.com/docs/en/hooks#stop-input .

## Account strip (0.4.1)

`ui/account_status.lua` uses `strip=true` and the bundled automatic strips loop;
never overwrite a custom layout. `accounts_ui.py` preflights both owned Lua files
before delivery and preserves unknown edits. Run capability is separately granted
by the user for this strip. Codex's default label requires no capability.
`pane.py` emits an indicator bound to the actual selected session's native UUID,
agent, local backend and cwd, independent of the login picker or owner mapping.
Never authenticate during refresh. Unknown Claude accounts remain unverified;
failed switches name the last confirmed profile. Validate with
`python3.11 examples/account_status_smoke.py` and the guided pane smoke.

## Simple session flow (0.5.0)

`simple.py` binds named native starts to a single-account guarded record before
launch. `agent_install.register_profiles` additively registers named agents after
verified login; preflight duplicate labels/custom registry edits. `creation_ui.py`
adapts only recognized stock/owned New session Lua, preserving native project and
worktree choices, hiding the internal guard and removing wrapper paths from labels.
The modified new_session pane requires user-granted Sessions; its permission dialog
must let settings actions through and cancel cleanly. Never grant capabilities.

`ui/account_switch.lua` is a separate float (floats cannot also fill a strip);
`account_status.lua` keeps the visible strip and opens it. Frozen five-minute plans
pin owner, UUID, identity/group, native/primary cwd and additional dirs. First switch
retains explicit group consent and valid native proof; selecting a previously
approved account can confirm directly. Cache only actually verified exact proof
contracts by full account identities/build/order, never synthesize one in production.
A single-account start does not need a cross-account proof. New history remains in
its native directory until guarded first-switch enrollment. Preserve multi-repo
working directory/add-dir context and stale-owner refusals after enrollment.

Stop hooks may continue generation. Idle switching requires a later Notification
idle_prompt and known-empty scheduled-work registry, not Stop alone. Source remains
running on active/unknown work or timeout. Quota path retains existing guarded stop.
See https://code.claude.com/docs/en/hooks#notification and #stop-input. Track native
scheduled wakeups and quota_auto_resume_fired as well as tool/subagent/background
work. Keep native guard settings/policies and process-lifetime lease intact.

Validate unit/compile/distribution, `examples/inline_switch_smoke.py`, strip and
guided-pane smokes, and `examples/shared_smoke.py --simple --desktop` plus legacy
`--mode --desktop`. Inline UI smoke has synthetic receipts/no-op create only;
tmux smoke uses real synthetic processes, not real Enterprise auth/model quota.
