# Thurbox Accounts

A standalone Thurbox extension for switching between Claude Enterprise accounts.
Each profile has a separate native SSO login and configuration directory. Start
new sessions under a selected account, or explicitly preview and confirm a
conversation handoff. Includes the Accounts pane (Alt+F7).

## Install

Requires Python 3.11+, Claude Code 2.1.268+, Thurbox 2.75.2+ and local tmux.

```sh
thurbox-cli extension install git+https://github.com/oks-erm/thurbox-accounts.git
# Use the installed launcher, or link it into a directory on your PATH:
mkdir -p ~/.local/bin
ln -s ~/.config/thurbox/extensions/thurbox-accounts/bin/thurbox-accounts ~/.local/bin/thurbox-accounts
thurbox-accounts ui-install
```

For a local checkout, use `thurbox-cli extension install /absolute/path/to/thurbox-accounts`.
In Thurbox Interface settings, grant the Accounts pane run/program capabilities
yourself. Installation does not grant them. Existing edited panes are preserved.

## Use

```sh
thurbox-accounts add work --label 'Work Enterprise'
thurbox-accounts login work
thurbox-accounts start work --repo /absolute/project --name work-project
```

[Account setup, pane keys and handoff guide](docs/ACCOUNTS.md). Handoff sends the
selected context to the target organization and requires explicit confirmation.
Credentials stay native; managed policies remain in effect.

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
```

The live smoke uses real Thurbox/tmux with synthetic accounts, without LLM calls.
Real Enterprise SSO and cross-organization transcript portability require user
login and `verify-handoff`; they have not been verified in this development run.
