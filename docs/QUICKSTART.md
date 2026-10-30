# Thurbox Accounts: colleague guide

Run Thurbox and the extension in the same WSL terminal environment (or local
macOS/Linux). Requires Python 3.11+, Claude Code and local tmux.

## Install once

Your GitHub account needs access to this private repository.

```sh
git clone https://github.com/oks-erm/thurbox-accounts.git
cd thurbox-accounts
./bin/thurbox-accounts install
```

Open Thurbox. In **Settings → Interface**, allow these permissions once:

| Pane | Allow |
| --- | --- |
| `new_session` | Sessions |
| `accounts` | Run, Program |
| `account-status` | Run |
| `account-switch` | Run |

Each dialog offers **Open Settings** if its permission is missing.

## Sign in, start, switch

1. **F7 → Add account → Log in.** Use a distinct name, such as Work A. Repeat for Work B.
2. Before using up account allowance, click **Prepare switching…** in Accounts,
   select the accounts and review the optional compatibility check. It consumes
   allowance for synthetic requests; it does not send your work.
3. **Ctrl+N → choose project and name → Claude — Work A → Create.**
4. In the conversation, click **Switch account → Work B**. Approve the listed
   accounts/organizations once so they can use that conversation's context.
   Subsequent switches between approved accounts need no new sharing setup.

Finish tools, background jobs and permission prompts before switching. An idle
switch can wait about a minute for Claude to confirm it is idle. A usage-limit
switch uses the quota signal. If a required compatibility check fails because an
account is exhausted, wait for its allowance to reset; the source stays unchanged.

Use named Claude choices for this flow. Default/unmanaged and old sessions need
[advanced attachment](../README.md#advanced-attach-older-unguarded-conversations).
Codex remains on its default account.

## Update

In the cloned repository:

```sh
git pull --ff-only && ./bin/thurbox-accounts install
```

Press **F10** in Thurbox. No account logins or conversation history are erased.
