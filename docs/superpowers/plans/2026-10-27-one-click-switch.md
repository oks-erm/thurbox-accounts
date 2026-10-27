# One-click Switch Implementation Plan

> Use superpowers:executing-plans inline; independent review before push.

**Goal:** Implement the approved selected-history, manual one-click account switch.
**Spec:** ../specs/2026-10-27-one-click-switch-design.md
**Architecture:** `shared.py` owns selected canonical history, enrollment and
switch operations; `guard.py` owns native process lifetime locks and hook state;
`shared_probe.py` proves native cross-profile resume/compaction before enabling.
The installer registers an additive guarded Claude agent. Existing handoff stays.

## Constraints and review rulings

- Keep account credentials/settings separate; only explicit enrolled history is shared.
- One-time consent binds ordered profile identities. Manual clicks cycle that order.
- No snapshot/fork/model request per switch; same conversation UUID/cwd.
- Hold transition lock across stop/start; durable allowed-owner reservation handles
  controller crashes. Target guard owns the writer lock before transition releases.
- Guard tracks native turn/tool/permission/subagent hooks. Stop only after freezing
  the native parent and finding a native usage-limit failure with no active workers;
  unknown/busy state refuses and resumes the original process.
- Guard holds writer lock for child lifetime, validates aliases on exit/start and
  refuses replaced links. Keep unexpected files for recovery; never merge silently.
- Exact-binary/profile proof must include A→B→A, writes, compact_boundary and aliases.
  Zero configured accounts means real authentication proof cannot run here.

## Tasks

- [x] Write regression tests for selected-only aliases, identity/proof gates,
  continuous reservation, contention, safe-state refusal and same-UUID switches (RED).
- [x] Implement canonical store/controller, guarded launcher and native hook merge.
- [x] Add opt-in native proof command, enrollment/switch CLI and native pane actions.
- [x] Add additive guarded-agent registration, manifest payloads and short docs.
- [x] Run full tests, fresh install/plugin check and real tmux synthetic switch smoke.
- [x] Independent review and important fixes. Commit/push and CI inspection are
  recorded in the completion report.
