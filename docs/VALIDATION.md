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
