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
