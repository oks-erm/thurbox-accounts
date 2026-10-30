# Validation

The split preserves the existing account/auth/handoff behavior and private state
format. All account services, CLI and pane delivery are independent of the
workflow extension. Python 3.11 standard-library unit/distribution tests verify
profile isolation, auth overrides, stale/expired/single-use confirmations, failure
recovery, UI ownership, Unicode paths and copied-payload operation.

The real tmux smoke uses synthetic Claude identities and no model calls. It
checks persisted profile environment, native-fork command routing, destination
UUID/restart and unchanged source transcript. It does not verify actual
Enterprise login or cross-organization transcript portability. Those remain
behind user SSO and the per-native-build verification gate.

Before the split, official Claude Code 2.1.308 signed-out status correctly
identified an isolated configuration directory. The native handoff gate remains
closed without login and a successful authenticated probe.

## Standalone extraction results

- 22 standalone tests pass, including installed-payload isolation and rebinding
  a recorded legacy pane without changing profile metadata.
- Python compile checks pass; the wheel builds without new dependencies and
  contains the Lua resource and only account runtime modules.
- Real Thurbox/tmux synthetic smoke passes. Artifacts:
  `/private/tmp/tbx-account-smoke-0n9st52y/summary.json`.
- Standalone extension installed as 0.1.0; the owned live pane was backed up and
  rebound to its launcher. Plugin check passed with zero warnings/dropped pills.
- Independent split review found no actionable regressions. Original workflow
  extension now ships only its workflow payloads as 0.2.1 (51 tests pass).
- Account data paths and capability grants were preserved. Real SSO remains
  unverified; no actual Enterprise conversation was transferred.

## Installer fix — v0.1.1

Reproduced the previous README Git install command on Thurbox 2.75.2 in an
isolated profile: exit 1 with `is a repository: it is cloned, not fetched file
by file`. The upstream extension loader rejects Git sources before cloning;
this is a command failure, not a TUI crash. The prior local-path installation
test did not cover that advertised Git install route.

The README now uses explicit Git clone plus the checkout's `install` action.
This installer reports stages, stops on failure, initializes a first-use
interface with the public CLI, validates the pane and preserves command links
on rerun. No running TUI, login, credential reads or capability grants needed.

26 tests and compile checks pass. Real first-install and repeat-install tests
passed with both an empty custom interface and the default interface path in
isolated configurations. Latest fixture: `/private/tmp/tbx-install-default-ui-4pmkmpy_`.
Independent review found no blockers; relative CLI/account paths are normalized
before invoking the installed launcher. Authentication behavior is unchanged.

## Shared sequential switching — v0.2.0

42 unit/distribution/installer tests pass, including a full synthetic subprocess
run of the guarded native verification protocol. New regressions cover selected-only
shared aliases and sidecars, proof/consent gates, replaced canonical parents,
active tool/permission/subagent refusal, stale destinations, transition contention,
reservation recovery, optional-focus failure and orphan-PID preservation. Compile
checks and diff whitespace checks pass. No new dependencies.

Real Thurbox 2.75.2/tmux synthetic A→B→A smoke passed with the same native UUID,
canonical transcript, separate profile environments, guarded quota shutdown and
stale managed writer rejection. Artifact:
`/private/tmp/tbx-shared-smoke-z8nsbikj/summary.json`.
The fixture uses a synthetic Claude executable and synthetic hook events; it
does not prove native Enterprise authentication or actual quota detection.

No real account profiles are configured locally. Native `verify-shared` and
authenticated cross-account compaction/sidecar behavior remain unverified here.
The production proof gate remains closed until users log in and that command
passes against their exact native build and selected account identities.

The 0.2.0 live installer and repeat install pass. Native Thurbox hook-only registry
patches are accepted without rewriting user settings; custom patches still refuse.
Live plugin check reports zero warnings and dropped pills. Legacy handoff smoke
also passed: `/private/tmp/tbx-account-smoke-g9yjjol2/summary.json`.

## Desktop companion — v0.3.0

55 Python tests pass. New coverage checks owned-only listing, enrolled-original
refusal, native foreground validation, literal input, transition-locked resume,
unconfirmed receipts without retries, cooperative deadline child cleanup, app
ownership/collision protection and interrupted enrollment recovery.

The SwiftUI/AppKit app compiles for macOS 13 on Apple Silicon and is locally
ad-hoc signed; `codesign --verify --deep --strict` passes. The installed app's
`--bridge-check` returns the expected empty real-profile snapshot;
`--ui-model-check` confirms draft isolation. Native window inspection confirms
the account/setup controls and empty state render. No capabilities were granted.

Real tmux synthetic smoke with `--desktop` passes listing/capture, guarded
Stop/Resume, literal prompt delivery, A→B→A and enrolled-original/stale-owner
refusals. Artifacts: `/private/tmp/tbx-shared-smoke-x_c7jina/summary.json`.
Synthetic console submission can be unconfirmed; the adapter displays that
receipt without retrying or claiming confirmed submission.

Installed: `~/Applications/Thurbox Accounts.app`, backed by the installed extension.
SSO and actual native cross-Enterprise behavior remain unverified: no real
profiles are configured. The native proof gate remains closed.

## Accounts shortcut fix

Removed Alt+F7 and its modifier glyph from the Accounts control; plain F7 now
opens/closes Accounts. Live plugin check reports no conflicts, warnings or
dropped pills. Seven UI-delivery/installer tests pass. An isolated real TUI
received F7 terminal input and changed focus agent → accounts → agent.
Fixture: `/private/tmp/tbx-f7-check-opqmqooy`. No sessions, model calls or grants.

## Current-conversation mode — v0.4.0

77 Python tests and compile/diff checks pass. Coverage includes untracked source
identity/directory verification, stopped-source requirements, bounded sidecars,
symlink/collision/source-change refusal, single-use expiring consent, Off/On,
transition serialization, original resume refusal and honest failed-account labels.
Real Thurbox/tmux with synthetic Claude passes ordinary adoption, unchanged
original files, mode Off refusal, On restore, A→B→A, same native UUID/canonical
history, separate profile environment, desktop adapter and stale-writer refusal.
Artifacts: `/private/tmp/tbx-shared-smoke-8cdcwbv4/summary.json`.
Real isolated Lua VM/PTY smoke passes frozen mode consent, missing-proof block,
paid-check review, On/Off/named switch, keyboard setup, F7 login return,
80x20 primary buttons/forms and refusal of consent in a short pane.
Artifacts: `/private/tmp/tbx-guided-6f27kzm4`.
No real native authentication/model calls, WSL execution or Enterprise account
portability were verified on the connected Mac. Native proof gates remain intact.
The 2.75.2 live checker emits its generic raw-click catalog warning despite
semantic actions; loading and layout validation still succeed. No auto grants.

Independent review found source-preflight races and stale/unresolved selection.
Failing regressions reproduced them; fixes now recheck full source before move
and prepared source after slow launch checks, and fail closed on native selection
changes/unresolved owners. Async Bash safety regressions also passed after retaining
background task evidence until structured native completion. Unknown completion
remains blocked. Real tmux rerun: `/private/tmp/tbx-shared-smoke-hcf6maak/summary.json`.
Post-fix real TUI: `/private/tmp/tbx-guided-jpah6y6w` (including stale selection and
unresolved-owner checks). Native hooks reference: [Stop input](https://code.claude.com/docs/en/hooks#stop-input).

Final checks: 82 Python tests pass; compileall/diff check pass. Final synthetic
tmux smoke also verifies background refusal through the actual native hook bridge:
the existing native process remains alive while background completion is unknown,
then A/B/A succeeds after a structured native Stop registry confirms completion.
Artifacts: `/private/tmp/tbx-shared-smoke-xhgx742s/summary.json`.
A real Claude CLI cold status probe against an empty private temporary config
returned signed-out status and the expected config-directory schema; no login or
model request was made. Actual Enterprise SSO and WSL execution remain unverified.

## Account strip 0.4.1

- 88 Python unit tests pass, including stale bindings, last-confirmed mode records,
  unknown failed legacy switches and preservation of custom status panes.
- Compile checks and `git diff --check` pass.
- `examples/account_status_smoke.py` uses a real isolated Thurbox 2.75.2 Lua VM/TUI
  with read-only fixture data. The strip occupies one visible row while Agent is
  focused; Codex/default, A→B labels, empty selection, loading and failure pass.
- Existing `examples/guided_pane_smoke.py` passes with the additional strip.
- Fresh local install, repeat install and live Mac plugin check pass. Existing
  generic raw-on_click warnings remain in Accounts and the custom Sessions pane.
- No authentication, model calls, capability grants or real Enterprise quota
  switches are exercised. WSL is not available on the connected Mac.
