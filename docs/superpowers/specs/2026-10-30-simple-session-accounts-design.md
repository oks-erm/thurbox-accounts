# Simple account selection and switching

## Intent

Colleagues should create and use Thurbox sessions without understanding account
bindings, native UUIDs, mode enrollment or terminal commands. The user chose the
normal New session (Ctrl+N) flow, rather than a second creation flow in Accounts.

## User flow

1. Accounts is for adding, naming and signing in to accounts. It shows whether
   each login is ready, and offers a separately confirmed compatibility check
   for the selected switching group before people begin work. Explain allowance
   cost and progress in that screen. Never run model checks merely on login.
2. Ctrl+N keeps Thurbox's normal project/worktree/name choices. Its agent/account
   picker offers recognizable choices such as `Claude — Work A`, `Claude — Work B`
   and `Codex — default`. Internal guarded launchers and executable paths must not
   appear as normal choices. An existing default Claude option remains available
   and is explicitly labeled default/unmanaged; it is not silently assigned.
3. Selecting a named Claude account starts the session with that isolated login
   and records its account before native Claude starts. New named sessions have
   lifetime guard hooks from their first turn, so a later switch does not require
   a second terminal. The conversation strip shows its actual account immediately.
4. The strip offers a real `Switch account` button while the conversation remains
   visible. It opens a compact account chooser, excluding the current account.
   No F7 detour, raw IDs, separate mode toggle, or terminal commands are required.
5. For the first switch, show the exact source/target accounts and organizations
   and ask permission for those accounts to access this conversation's history.
   Preserve the existing frozen single-use confirmation contract. A missing
   compatibility proof offers a separately confirmed check here; an exhausted
   source may prevent that check, so the UI recommends preparing accounts first.
   Never imply that initial verification is free or guaranteed after quota.
6. On confirmation, the extension checks readiness and safely pauses only its
   guarded native parent, then resumes the same UUID/history under the target.
   Active tools, background tasks, subagents, permission prompts, failed hooks or
   unknown completion refuse the operation and leave the source running.
   A confirmed idle or quota-stopped turn can switch. Display progress and failure
   in the chooser. Focus the replacement session automatically on success.
7. Subsequent switches to previously approved accounts use that approval without
   extra context copies, model requests or per-switch forks. Choosing an account
   outside the approved group requires a new explicit sharing review and a valid
   compatibility proof. Switching remains manual, not automatic rotation.

## Approaches

- **Chosen: extension integration with the normal New session flow.** Register
  owned named-account agent choices, use a guarded profile launcher, and apply a
  small checked UI adapter to present clean labels/hide internal launchers. Reuse
  the existing account strip as the entry point to a compact switch chooser.
  This preserves normal project/worktree creation and avoids a new Thurbox binary.
- **Separate Accounts creation wizard.** Less integration work, but repeats the
  confusing split workflow the user rejected.
- **Fork the Thurbox binary.** A native extension hook could be cleaner long term,
  but distributing/updating another executable is too costly for colleagues when
  the existing agent registry and Lua interface can support the flow.

The user selected normal New session. The precise launcher/UI integration above
is the proposed implementation choice, subject to validation against the public
registry and Lua contracts before delivery.

## Implementation boundaries

Keep this in the standalone thurbox-accounts repository, Python standard library
and Lua, targeting local WSL/tmux plus the connected Mac for development tests.
Do not modify auth credentials, managed policies, sandbox/trust settings or the
native default agent. Do not add a runtime dependency.

Named new sessions must be supervised from their first turn. Reuse/refactor the
existing lifetime writer lease, native hook reducer and stopped-worker evidence;
do not invent a weaker way to infer idle from terminal text. A single-account
session may start without cross-account compatibility proof, but adding another
account must retain identity/build/proof/consent checks. Persist approved scope
and transition reservations before cross-account aliases or processes are created.

Use one canonical UUID history once prepared for switching. A fresh single-account
session must remain single-account until explicit approval. Recovery preserves
last-confirmed account evidence and refuses competing/stale writers. Do not erase
history or silently expand an existing approval when the available logins change.

The UI installer must back up and update only recognized pristine or owned files,
preflight every destination before mutation, preserve custom layouts/libraries and
refuse unknown edits with an actionable message. Never grant capabilities itself.
Use existing automatic strips and supported modal/node APIs. Document any new
one-time UI permission clearly. Account registration must be additive/idempotent
and preserve unrelated agent definitions and custom args/policies.

## Existing conversations and limitations

Existing shared conversations keep their approvals, history and guard behavior.
Existing unguarded/default sessions are not silently relabeled or terminated.
The switch chooser identifies these and offers explicit identity verification and
attachment only when a stopped, worker-free source can be proven by existing
policy. If that cannot be proven, explain the limitation rather than offer a
misleading working Switch button. Primary acceptance is new named-account sessions
created through Ctrl+N; retrofitting arbitrary running sessions is not promised.

Remote hosts, native PowerShell and account routing for Codex are out of scope.
Codex retains `default`. No automatic quota-based switching is added.

## Validation and delivery

Test named profile dispatch, persisted identity, startup/restart ownership, failed
and stale launches, identity/build changes, single-account start without proof,
and consent/proof refusal before cross-account changes. Test idle/quota switches
and refusals for tools/subagents/background jobs/unknown state with real synthetic
native processes and tmux. Validate the actual Ctrl+N and inline chooser in an
isolated real Lua VM/TUI, including keyboard, clicks, cancellation, small screens,
provider/default behavior and installer fresh/rerun/custom-file preservation.

Run full unit/compile/distribution checks, plugin check, review the diff, install
on the connected Mac, commit/push and inspect GitHub CI. Report that real Enterprise
SSO/quota portability and WSL were not directly verified when unavailable. Provide
a brief colleague-facing guide: sign in once, Ctrl+N choose account, Switch account.
