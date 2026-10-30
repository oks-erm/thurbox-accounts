# Thurbox Accounts

A standalone Thurbox extension for switching between Claude Enterprise accounts.
Each account has its own native SSO login. Choose a named account in normal
**New session (Ctrl+N)**, then use **Switch account** beside the conversation's
account label to continue the same history under another account.

**For colleagues:** use the [short setup guide](docs/QUICKSTART.md).

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

Open Thurbox (press **F10** if already running). In **Settings → Interface**,
allow **Sessions** for `new_session`, **Run/Program** for `accounts`, and **Run**
for `account-status` and `account-switch`. These are one-time permissions; the
installer never grants them. The dialogs link to Settings if permission is missing.

## Start and switch accounts

1. **F7 → Add account → Log in.** Repeat for each account with a distinct name.
2. Optional, before using up either account: **Prepare switching…**, choose the
   accounts, and review the compatibility check. It uses synthetic model requests
   and account allowance; it never sends an existing conversation. Valid checks
   are reused for the same accounts and native build.
3. **Ctrl+N**, choose your project/name, then **Claude — Work A** in **Agent / account**.
   The conversation shows **Account: Work A** from startup.
4. Click **Switch account** in the conversation strip and choose **Work B**.
   The first switch asks which accounts/organizations may access this history.
   Later switches to those approved accounts continue directly.

No separate switching-mode setup or second terminal is needed for these named
sessions. Working tools, background jobs, scheduled wakeups and permission prompts
block switching. Usage-limit switches use the guarded quota signal. An idle switch
can wait about a minute for Claude's independent idle notification; a Stop hook
alone can continue generation and is not treated as proof of idle.

If compatibility was not checked before an account reached its limit, the initial
check may fail until that account is available. The UI explains this and leaves
the conversation on its current account. Use the named choices for new work;
`claude (default / unmanaged)` retains Thurbox's original login and requires the
advanced attachment flow below. Codex uses its default account.

A recognized stock/owned New session pane is adapted with a backup. Custom edits
are preserved and installation explains how to restore the stock pane before
retrying. No Thurbox fork or shared library/layout edits are required.

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

## See the current account

A one-line **Account:** strip stays visible above the bottom buttons while you
work. It follows the selected conversation, independently of the account selected
in the Accounts pane for new conversations. Tracked Claude conversations show the
account name; Codex shows **default**. An untracked Claude login shows
**unverified**, and a failed switch shows the **last confirmed** account.

After updating, press **F10**. For Claude labels, allow **Run** for
**account-status** in **Settings → Interface** once. The strip only reads local
metadata; it never signs in or sends a model request. Codex needs no permission.
The strip uses Thurbox's automatic strips layout; custom layouts that removed
that loop must restore it before the strip can appear (`plugin check` explains).

## Accounts and older conversations

**F7** manages logins and offers the optional compatibility preparation. Selecting
a login here does not change a running conversation. Use Ctrl+N for new work and
the conversation's **Switch account** button for changing accounts.

The advanced conversation controls remain for older sessions. Install/update
inside the same WSL environment where Thurbox runs; updating a Mac does not update
another computer.

## Advanced: attach older unguarded conversations

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
