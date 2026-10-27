# One-click account switch

## User-approved intent

Use accounts sequentially. When the current account reaches its usage allowance,
click once to continue the same local conversation under another account. The
user explicitly chose a manual button rather than automatic quota failover.

## Proposed design

- Enable sharing once for a conversation and an explicit ordered set of accounts.
  Show that those accounts can use its context. Later clicks require no handoff
  preview/confirmation cycle for that already approved set.
- Keep credentials, settings and each account's CLAUDE_CONFIG_DIR separate.
  Share only the selected conversation's history and required session sidecars.
  Never link whole account/configuration or project-history directories.
- Maintain one canonical local conversation directory and conversation UUID.
  Managed references in participating profiles point to it; switches do not
  snapshot/fork the history or issue a model acknowledgement request.
- The button names the next account. Validate its login before stopping the
  current process; refuse while tools/permission prompts are active or state
  cannot safely establish a switch point. Stop and verify the source is gone,
  then resume the same UUID and working directory under the target profile.
- A managed launcher holds a per-conversation exclusive lock for its process
  lifetime, including restart. A competing managed process must refuse to launch.
  Do not claim to constrain direct Claude launches outside the managed extension.
- Resume at the interactive prompt; do not replay tool calls or automatically
  submit a model request. The next user request sends restored context using
  the selected account. Switching accounts does not enlarge the context window.
- Persist an operation/recovery record before changing references or launching.
  Failure retains all history, reports the exact failed stage and leaves no
  second managed writer. Preserve the existing explicit handoff command for
  backwards compatibility while shared sessions are introduced.

## Alternatives considered

1. Existing snapshot/fork per switch: preserves isolation, but duplicates history
   and makes an extra model request; does not match the requested seamless flow.
2. Shared selected-conversation storage with separate logins: recommended for the
   requested one-at-a-time use. Requires native compatibility validation.
3. Sharing the entire configuration directory: mixes login state and settings,
   so it cannot provide reliable account switching.

## Proof required before enabling

Claude documents resume by ID/transcript path, but does not promise safe shared
transcript writes across account directories. Test native A → B → A with the same
UUID and canonical file, appended history, compaction/sidecar behavior, restart,
lock contention and failed launch recovery. Never silently enable it based only
on help flags or synthetic agent tests. If native behavior fails, report the
limitation rather than introducing hidden transcript rewrites or credential copies.

No profiles are configured locally at the time of this design. Full validation
will require user SSO for the accounts; never read/import their credential files.

## Scope

Account-switching extension only. Native CLI helpers/Lua pane and necessary
managed-launcher integration may change. No provider-policy bypass, automatic
account rotation, unrelated workflow features or global account-history sharing.

## Approved and review rulings

User approved implementation. Manual clicks cycle the configured order; there
is no automatic retry loop. A transition owner holds its lock until the target
has acquired the process-lifetime writer lock. A durable allowed-owner reservation
blocks unrelated launches after a controller crash. The guarded native supervisor
uses turn/tool/permission/subagent hooks for safe state; it freezes its own native
parent before accepting a stop, refuses unknown/active work, then performs shutdown.
Unexpected native alias replacement is a hard recovery error; no automatic merge.

## Implemented safety refinement

An ordinary Stop hook may request more work, so it does not authorize an automatic
shutdown. Only notification-only StopFailure `rate_limit`, with no active tools,
subagents or permission block, authorizes it; otherwise the user must stop at a
safe point before switching. The supervisor preserves unconfirmed startup/native
PID evidence after a crash and refuses direct same-owner restarts too.
The native probe exercises the guarded launcher, contention and failed-start
recovery with synthetic context. The public Thurbox integration is separately
exercised by the real tmux synthetic smoke; real Enterprise quota behavior remains
unverified here and must not be claimed from that smoke.
