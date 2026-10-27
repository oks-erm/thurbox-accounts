# Desktop Companion Implementation Plan

> Use superpowers:executing-plans inline; fresh independent review before push.

**Goal:** A native Mac window for the existing guarded account/conversation flow.
**Architecture:** Python desktop adapter with narrow owned-session operations;
SwiftUI views invoke the installed CLI through a bounded Foundation Process bridge.
**Tech Stack:** Python 3.11 standard library, SwiftUI/AppKit, macOS 13+.
**Spec:** ../specs/2026-10-27-desktop-companion-design.md

## Constraints and review focus

No new auth provider or dependencies; preserve proof, consent and writer guards.
No model call on refresh. Do not send into foreign, stale or stopped sessions.
Literal prompts beginning with dashes/newlines must survive argv transport.
Native browser SSO remains interactive; UI cannot silently accept trust prompts.
Slow/failing backend work must leave a responsive UI with visible errors.
Install only owned app bundles; preserve unrelated targets and support reruns.

## Tasks

- [x] Adapter: add tests for owned listing, array session JSON, stale writer input,
  literal send/key allowlist; run red, implement desktop.py/CLI and run green.
- [x] Native app: implement accounts/conversation/composer/setup actions, async
  bounded bridge, consent and paid verification alerts. Compile and run bridge test.
- [x] Delivery: owned app builder/desktop-install, manifest/resources, version and
  short README/AGENTS docs. Test fresh/repeat install and collision preservation.
- [x] Validate full suite/compile, synthetic real-tmux desktop flow and native UI.
  Fresh review, fix important issues, install/push and inspect CI.

Ruling: native console output uses a vertical, wrapping text view; full terminal
emulation would add a dependency and is outside this account-switching companion.
Push/CI inspection is recorded in the completion report.
