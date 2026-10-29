# Current-conversation switching mode

## Intent and chosen approach

The user uses Thurbox in WSL and chose a mode for the current conversation.
Make an existing local Claude conversation switchable without recreating it or
manually configuring session IDs. Preserve the earlier choice of one-click
switching at quota; enabling this mode does not automatically rotate accounts.

Approaches discussed: per-conversation opt-in (chosen), or global opt-in for all
eligible conversations (rejected for this scope because it grants broader
organization access). Build on the Python CLI/backend and Lua pane; no new
runtime dependencies, daemon, or change to Claude authentication.

## Experience

Opening Accounts shows the conversation selected in Thurbox, its actual current
account when verified, and `Account switching: Off / On`. Account selection for
login/new conversations is labeled separately from the current conversation.
Do not hide an existing conversation simply because Accounts did not create it.
An unsupported agent/remote session gets an explicit explanation.

Enable opens a review for this exact conversation and the chosen account order.
Show friendly labels plus verified identities/organizations where available.
Explain that these organizations can access this conversation's context, that
logins stay separate, and that switching requires a safe stop. Freeze the native
UUID, source session, history identity and account order in this confirmation.
Recheck them before any change; stale confirmation must be refreshed.

Once approved, the helper performs the needed setup, reusing valid compatibility
proof. If proof is missing, explain the paid synthetic checks and require their
explicit approval before running them. Never send a model request on refresh or
merely selecting an account. Proof failure leaves the source untouched and shows
an actionable reason. A quota-exhausted account may prevent initial verification;
do not claim this mode can bypass that limitation.

Only after successful enrollment show `On` and a prominent named `Switch to …`
button. A switch resumes the same native conversation UUID and canonical local
history under the next approved account; no fork or per-switch history copy.
Actual current account updates only after successful launch. Show failures rather
than leaving a misleading `Selected` label as apparent evidence of a switch.

Off preserves the running account/history and prevents future cross-account
switches for this mode-managed conversation, including explicit CLI switch.
It does not erase history or undo context access already granted to organizations.
Off changes are serialized with transitions. If a transition failed or native shutdown
is uncertain, show recovery guidance rather than claiming the old account is active.
Recovery must not start another account while Off.
Existing records not created with this mode retain their previous manual behavior.
Re-enabling the unchanged approved group needs no repeated paid check if its
proof/identity/build remains valid. Changing group requires renewed consent.

## Existing ordinary conversations

Use public Thurbox session/launch metadata and native Claude auth status to verify
source directory, native UUID, transcript, cwd, identity and matching selected
account. Never infer the source account from the UI's account picker. Do not read
or copy credentials or broad configuration directories. Refuse an unverifiable
source, API/provider authentication, remote session, mismatched identity, foreign
history ownership, symlinked inputs or conflicting target UUID.

The source must be stopped safely. Do not force-stop tools, shell jobs, subagents,
permission prompts, unknown work, or use an `Idle` label alone as shutdown proof.
For an untracked original, take one validated initial snapshot of only its history
and required native UUID sidecars into canonical storage, preserving its original
files. Link only approved profile history paths to that canonical conversation.
This one initial snapshot is distinct from switching, which never recopies it.
Persist recovery metadata before filesystem mutations. Recheck source unchanged
before starting the guarded owner. Keep the original stopped and distinguish it
from the new managed owner; never resume the original through the Accounts UI.
Give the managed row the original friendly conversation name with a clear
`(switchable)` suffix rather than an opaque generated name. Do not delete the old row.

Reuse existing identity/build proof, transition serialization, native supervision,
durable reservations, writer lock and shutdown checks. Do not weaken them to make
the toggle appear to work. Other conversations, profiles, hooks and trust settings
remain untouched. Rollback/recovery must preserve files and report uncertainty.

## Validation and delivery

Test adoption from ordinary sessions, source identity mismatch, live/unknown
workers, source changes during confirmation, target collisions, failed setup,
off/on round trips and refusal to switch while off. Verify UUID/history continuity
and distinct account environments through real Thurbox/tmux using synthetic Claude.
Exercise the toggle and switch in an isolated real Lua VM/TUI, including small
panes. Run full Python/installer checks, independent review and live plugin check.
Install the verified version on the connected Mac, commit/push as already requested,
and inspect CI. WSL installation and genuine Enterprise SSO cannot be certified
from the Mac; provide a brief update command and report that limit honestly.

Builder check: no important user questions remain; explicitly cover disabled-mode
recovery after failed transitions. That requirement is included above.
