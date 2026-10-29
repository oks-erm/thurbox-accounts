# Thurbox Accounts

A standalone Thurbox extension for switching between Claude Enterprise accounts.
Each profile has a separate native SSO login and configuration directory. Start
new sessions under a selected account, or enable one-click switching on a
selected conversation with one shared local history. Includes the Accounts pane (F7)
and an On/Off mode for existing local conversations in WSL, macOS and Linux.

## Install

Requires macOS or Linux (Windows: use WSL), Python 3.11+, Thurbox 2.75.2+, local tmux and a Claude Code build
that passes `verify-shared` (the current local native build is 2.1.308).

The repository is private: Git must have access through your GitHub login.
Clone it first, then run the installer from that checkout:

```sh
git clone https://github.com/oks-erm/thurbox-accounts.git &&
  ./thurbox-accounts/bin/thurbox-accounts install
```

If already cloned, run from inside that checkout:

```sh
git pull --ff-only && ./bin/thurbox-accounts install
```

The installer prints each stage, stops at the first failure, and safely supports
reruns. It installs the local extension, prepares/validates the Accounts pane
without opening Thurbox, registers the separate `claude-accounts` guarded agent,
and links `~/.local/bin/thurbox-accounts`. It preserves
unrelated commands and custom pane edits. If that directory is outside your PATH,
use the absolute command path printed on success.

For a nonstandard Thurbox location:

```sh
./bin/thurbox-accounts --thurbox-cli /absolute/path/to/thurbox-cli install
```

Then open Thurbox, press **F7**, and grant the Accounts pane run/program
capabilities in Interface settings yourself. Installation never grants them.

**Thurbox 2.75.2 installer issue:** do not use `extension install git+https://…`.
It fails with “is a repository: it is cloned, not fetched file by file” before
cloning. The installer above uses `extension install /local/checkout`, which
works on that version. `plugin install` is a separate command and does not install
this extension.

## Mac desktop companion

For a native window with account setup, conversation output, replies and a named
**Switch to account** button, run this after installing the extension:

```sh
thurbox-accounts desktop-install
open "$HOME/Applications/Thurbox Accounts.app"
```

Requires macOS 13+ and Apple's Swift command-line tools. If needed, install them
with `xcode-select --install`, then rerun `desktop-install`. The app is compiled
locally with no third-party UI packages. An unrelated app at that path is preserved;
updates to this app keep a timestamped backup.

Inside the app:

1. Add an account name, click **Log in…** and complete native SSO in Terminal and
   your browser. Repeat for the other account; **Check login** confirms identity.
2. Select an account and click **New conversation…** to choose your project.
   Read the native console and answer its prompts yourself. **Send** submits a
   request; Enter/Esc/arrow buttons handle native menus and confirmations.
3. Expand **Set up shared history**, enter the account names in switching order,
   and click **Verify accounts…**. Its confirmation explains synthetic model usage.
4. Stop the conversation at a safe point, then **Enable for selected conversation…**.
   Confirm exactly which accounts can use its context. Later, click **Switch to…**
   when the current account reaches its limit.

The Thurbox TUI does not need to be open. The companion uses its local background
runtime and the same guarded sessions, history, native proof and recovery checks.
Drafts stay with their conversation. Refreshing never sends a model request.
If submission cannot be confirmed, the app shows that uncertainty: inspect the
native console before retrying or pressing Enter.

This is a companion window for Claude Code, not an injected modification to the
Claude Desktop app. It displays the most recent 300 native console lines rather
than a full terminal emulator. Advanced terminal editing remains available in
Thurbox. Browser/SSO login remains native; no credentials are copied.

To update: rerun the extension installer, then `thurbox-accounts desktop-install`.
Close and reopen the companion after updating. The native app pins the backend
paths from its build, so rerun that command if Python/Claude/Thurbox paths change.

## Use the Accounts pane

1. Press **F7**. Click **Open Settings** if the pane asks for its one-time permissions.
2. Enter a friendly account name (for example Work A), click **Add account**, then **Log in to Work A**. Finish Claude’s browser/SSO login; **F7** returns to your accounts. Repeat for the other account.
3. Click **Conversations → New conversation**, choose/paste your project folder, then **Create conversation**.
4. For an existing conversation, follow **Current-conversation mode** below.
5. Once its mode is On, click **Switch to ACCOUNT** when you want to change accounts.

Click controls directly, or use **Tab** and **Enter**. No Alt shortcuts, internal session IDs or comma-separated account names are needed. If a confirmation does not fit, enlarge the pane before continuing.

Install/update on the computer and terminal where Thurbox runs. Updating a Mac does not update a Windows/WSL copy.

## Current-conversation mode

1. Select your existing Claude conversation in Thurbox's session list. Finish any
   tools, shell jobs and subagents before setup. In a second WSL terminal, park
   the conversation safely with `thurbox-cli session stop CONVERSATION_NAME`.
   This keeps its history and checkout. Do not stop a session with work still running.
2. Press **F7**. The pane shows that existing conversation, even if Accounts did
   not create it. Click **Turn switching mode On…**, then choose the accounts in
   switching order and **Review and enable mode…**.
3. Review exactly which accounts/organizations can use its context. If a native
   compatibility check is needed, the pane asks separately before spending account
   allowance. An account already at its limit can block this initial check; the
   mode stays Off and explains why. A valid saved check is reused.
4. Approve setup. The pane prepares the history and focuses a guarded session
   named after the original with **(switchable)** and a short unique suffix.
   Click its named **Switch to ACCOUNT** button whenever needed.
5. **Turn switching Off** keeps the current account running and blocks further
   account switches, including the CLI. **Turn switching On** restores the same
   approved group without another paid check while its proof remains valid.

Selecting an account under **Logins / new conversations** only selects it for
login and new work; it does not change the account of an existing conversation.
The mode prepares switching automatically after approval; switching at a limit
remains one click, not automatic rotation.

Only the selected conversation is enrolled. For an untracked original, setup
keeps its original files unchanged and takes one initial snapshot of its native
UUID history/sidecars. Subsequent switches use the same UUID and canonical local
history without copying or forking it. Previously account-managed sessions retain
their existing move/link enrollment. Keep the old original stopped and use the new
managed session. Conflicting UUIDs, uncertain ownership, unsafe paths and active
work are refused; failed setup preserves recovery evidence. Off does not erase
history or undo organization access already granted.

Advanced CLI: `mode-preview --session NAME --profile work-a --profile work-b`
returns a five-minute confirmation token; `mode-enable TOKEN --consent` applies it.
Use `mode-off --session CURRENT_MANAGED_SESSION` and `mode-on --session CURRENT_MANAGED_SESSION`
for later toggles. Prefix each action with `thurbox-accounts`.

## CLI account setup

```sh
thurbox-accounts add work-a
thurbox-accounts login work-a
thurbox-accounts add work-b
thurbox-accounts login work-b
thurbox-accounts verify-shared work-a work-b
```

Log in to each Enterprise account in its native browser/SSO flow. `verify-shared`
uses **synthetic model requests and your account allowance**: six top-level calls
for two profiles, plus a subagent, with `--max-budget-usd 0.25` per top-level call.
It checks the exact Claude build, account identities, same-UUID resume, guarded
restart, writer contention, failure recovery, sidecars and compaction. Sharing
stays disabled if any check fails; rerun after changing accounts/order or Claude.
Run this while both accounts still have available allowance.

## Enable a conversation once

Start a session through Accounts, or:

```sh
thurbox-accounts start work-a --repo /absolute/project --name my-project
# Use its returned Thurbox session ID below; stop it at a safe point first.
thurbox-cli session stop SOURCE_SESSION_ID
thurbox-accounts enable-shared --session SOURCE_SESSION_ID --profile work-a --profile work-b --consent
```

This approves **both selected accounts/organizations using this conversation's
context**. It moves only this conversation and its sidecars into one private
local directory, links that history into the selected profiles and resumes the
same native UUID. Logins, settings and unrelated conversations stay separate.
Use the new guarded session returned by the command; leave the original stopped.

## Switch when the account reaches its limit

Open **F7**, click **Conversations**, select the shared conversation and click **Switch to ACCOUNT**. The pane shows the next account before switching. Switches cycle the
approved order, stop the source and resume the same conversation under the next
account. There is **no per-switch fork, history copy or extra model request**;
restored context is used when you next send a prompt.

CLI equivalent:

```sh
thurbox-accounts switch --session CURRENT_SHARED_SESSION_ID
thurbox-accounts shared-status --session CURRENT_SHARED_SESSION_ID
```

Switching refuses active tools/subagents, unconfirmed background shell jobs, permission prompts, unknown state or
unconfirmed shutdown. If native task completion cannot be verified, switching and
recovery stay blocked; finish the task in native Claude and inspect its status
before retrying. A native `StopFailure` with `rate_limit` permits the guarded
stop. If Claude reports a different limit/error, stop the session yourself at a
safe point, then switch. Crashed-supervisor evidence is preserved rather than
starting another writer. Never start direct Claude processes against shared
history; the lock protects managed `claude-accounts` sessions only.

If a target launch fails, inspect `shared-status`, then use:

```sh
thurbox-accounts recover-shared CONVERSATION_UUID
```

Recovery reuses the reserved session and account. Missing/replaced history links
or unconfirmed workers require manual inspection; no automatic merge or overwrite.
[Full account and legacy handoff guide](docs/ACCOUNTS.md).

## Upgrading from the combined extension

The command is now `thurbox-accounts ACTION` instead of `thurbox-loop accounts ACTION`.
The private state directory remains `~/.local/share/thurbox-loop/accounts` for
compatibility: no credential/profile copy or migration is needed. `ui-install`
rebinds the unchanged owned pane to this extension; custom edits are refused.
This repository contains only account switching and has no dependency on the
workflow extension.

## Development

```sh
python3.11 -m unittest discover -s tests -q
python3.11 -m compileall -q thurbox_accounts tests examples
python3.11 examples/live_smoke.py --thurbox-cli /path/to/thurbox-cli
python3.11 examples/shared_smoke.py --desktop --thurbox-cli /path/to/thurbox-cli
```

The live smoke uses real Thurbox/tmux with synthetic accounts, without LLM calls.
Real Enterprise SSO, native cross-account shared history and quota detection have
not been verified in this development run: no real profiles are configured here.
`verify-shared` is required before enabling shared history. Synthetic smoke results
do not certify native Enterprise behavior.
