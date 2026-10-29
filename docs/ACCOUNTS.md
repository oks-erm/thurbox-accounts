# Shared one-click switching

For sequential account use with one local conversation, follow the
[README setup and switching guide](../README.md#one-time-account-setup).
The handoff commands below are the older explicit snapshot/fork workflow.
They remain available but are not used by shared switching.

# Claude Enterprise accounts

Each named profile has its own private `CLAUDE_CONFIG_DIR`. Credentials stay in
Claude's native browser/SSO flow and credential storage. No keys are copied.
Use one profile per Enterprise identity/organization; managed policies still apply.

## Quick start

Requires Python 3.11+, Claude Code 2.1.268+, Thurbox 2.75.2+ and local tmux.
Account sessions explicitly use tmux.

```sh
thurbox-accounts add company-a --label 'Company A'
thurbox-accounts login company-a
thurbox-accounts status company-a
thurbox-accounts add company-b --label 'Company B'
thurbox-accounts login company-b
thurbox-accounts start company-a --repo /absolute/project --name project-a
thurbox-accounts start company-b --repo /absolute/project --name project-b
```

Login opens the official SSO flow. Check the email/organization reported by
`status` before starting work. The first successful identity is pinned; a changed
identity is refused. `list` shows profiles; `list --text` gives a compact list.
If an organization ID is unavailable, the email is pinned; verify the organization
in the browser. The CLI cannot independently certify the account's Enterprise tier.

## Thurbox panel

```sh
thurbox-accounts ui-install
```

Press **F7** to open/leave Accounts. In **Ctrl+, → ]**, select Accounts and
grant its **run/program** capabilities yourself. Installation never grants them.
Click **Add account**, give it a friendly name, then **Log in**. Complete native
SSO and press **F7** to return. Repeat for each account. Open **Conversations**
to create/open conversations or select **Turn switching mode On…** for the
current existing conversation. Select
accounts in switching order; **Check compatibility** and **Review and enable mode…**
each show an explicit confirmation. Later use the named **Switch to** button.
Use clicks, or Tab/Enter. No profile IDs or Alt shortcuts are required.
Enlarge the pane if the sharing confirmation cannot fit.

Windows users must run the extension and Thurbox in the same WSL environment.

The pane shares the existing center slot. It preserves the layout and shared
libraries. A replaced starter/previous generated pane is backed up beside it;
unknown custom panes are refused. Use Interface settings to disable the pane.

## Continue an existing conversation under another account

This sends the selected conversation's context to the **target organization**.
Only local Claude sessions created with `thurbox-accounts start` are eligible. Existing
untracked sessions must continue under their current account.

First verify the installed Claude build under the target profile. This makes two
small model requests using synthetic text, with tools disabled; each has a $0.10
budget. Repeat after a Claude upgrade or account identity change.

```sh
thurbox-accounts verify-handoff company-b
# Stop only after the source has finished its work and permission prompts.
thurbox-cli session stop SOURCE_SESSION_ID
thurbox-accounts handoff --session SOURCE_SESSION_ID --to company-b
# Read the preview, then explicitly confirm its single-use five-minute ID:
thurbox-accounts handoff --confirm PLAN_ID
```

Confirmation snapshots only the selected main transcript. Native Claude forks it
under the target identity with tools disabled for one acknowledgement request;
then Thurbox opens the destination using its new conversation UUID. That request
can incur normal account usage. Subagent histories, credentials, account settings,
other conversations and worktrees are not copied. Both sessions use the same
working directory, so files there remain visible to the target agent.

The original conversation stays stopped and unchanged. Plans expire, become
invalid on detected changes, and cannot be reused. A failed transfer leaves a
private operation record with a recovery command (`thurbox-cli session start
SOURCE_SESSION_ID`); inspect any partially created target before retrying.
Organization restrictions or unsupported native fork behavior leave handoff disabled.

## Storage and limits

Private state defaults to `~/.local/share/thurbox-loop/accounts`. Global options
go **before** the action: `thurbox-accounts --accounts-dir /private/path --claude
/path/to/claude --thurbox-cli /path/to/thurbox-cli list`. JSON is the default output.
No automatic quota failover, logout, profile deletion or policy bypass is provided.
Conflicting API-key/token/provider environment variables are refused by name,
without displaying their values. Restarting a session preserves its profile path.

Automated fixtures cover isolation, stale/expired confirmations, failure recovery
and native-fork command routing. Live tests without Enterprise logins cannot prove
cross-organization authentication or transcript portability; complete SSO and the
native verification before transferring real context.

## Current-conversation mode (0.4.0)

See the [short mode walkthrough](../README.md#current-conversation-mode).
Existing untracked local Claude sessions are visible when selected in Thurbox.
The source account is verified from its native directory/status, not the login
picker. Finish work and explicitly park the original before setup. One initial
snapshot preserves its original files; subsequent switches share canonical UUID
history. On/Off is per conversation and Off is enforced in the CLI too.
Switching mode is separate from automatic rotation; switching remains one click.
