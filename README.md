# Thurbox Accounts

A standalone Thurbox extension for switching between Claude Enterprise accounts.
Each profile has a separate native SSO login and configuration directory. Start
new sessions under a selected account, or explicitly preview and confirm a
conversation handoff. Includes the Accounts pane (Alt+F7).

## Install

Requires Python 3.11+, Claude Code 2.1.268+, Thurbox 2.75.2+ and local tmux.

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
without opening Thurbox, and links `~/.local/bin/thurbox-accounts`. It preserves
unrelated commands and custom pane edits. If that directory is outside your PATH,
use the absolute command path printed on success.

For a nonstandard Thurbox location:

```sh
./bin/thurbox-accounts --thurbox-cli /absolute/path/to/thurbox-cli install
```

Then open Thurbox, press **Alt+F7**, and grant the Accounts pane run/program
capabilities in Interface settings yourself. Installation never grants them.

**Thurbox 2.75.2 installer issue:** do not use `extension install git+https://…`.
It fails with “is a repository: it is cloned, not fetched file by file” before
cloning. The installer above uses `extension install /local/checkout`, which
works on that version. `plugin install` is a separate command and does not install
this extension.

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
