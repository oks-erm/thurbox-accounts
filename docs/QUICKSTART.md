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
   Click **Open sign-in page** above the login terminal if its long link wraps.
   The button opens the complete URL. Finish any native prompts, then return with F7.
2. **Ctrl+N → choose project and name → Claude — Work A → Create.**
   This chooses the main account. Switching is On from creation.
3. Click **Switch account → Continue on Work B**. Choosing the account approves
   its access to this conversation. Later switches work the same way.

The new conversation reads a private copy of saved context and current project
files using the chosen account. The source account sends no model request and
needs no allowance. Its session is left untouched. Recent excerpts and the complete
saved transcript are available in the common context store; earlier snapshots
remain linked across later continuations. Missing history refuses before creating
anything. The destination's context-reading turn uses its own allowance and normal
permissions. Restart resumes it without repeating the initial handoff prompt.
The paid compatibility diagnostic in Accounts is optional.

The Accounts pane's New session button opens the same main-account picker.

Use named Claude choices for this flow. Default/unmanaged and old sessions need
[advanced attachment](../README.md#advanced-attach-older-unguarded-conversations).
Codex remains on its default account.

## Update

In the cloned repository:

```sh
git pull --ff-only && ./bin/thurbox-accounts install
```

Press **F10** in Thurbox. No account logins or conversation history are erased.
