# Guided Accounts pane plan

> Use executing-plans inline; independent review before push.

Spec: ../specs/2026-10-27-guided-accounts-pane-design.md

- [x] Test/implement friendly account naming and percent-encoded read model,
  friendly bounded action receipts. Reuse existing policy and CLI routes.
- [x] Replace Lua pane with clickable Accounts/Conversations/setup confirmations,
  field click focus and selected account/conversation guards; no Alt key wall.
- [x] Update usage docs. Test Python suites, stubbed Lua behavior, real plugin check
  and isolated native TUI. Review, install, push and inspect CI.

Validation: 59 Python tests passed, compileall and diff checks clean. Isolated
real Thurbox VM/PTY smoke passed keyboard account creation, new-account selection,
ordered account selection, verify cancellation, consent gating, 10-row refusal,
F7 login return, and Create/Cancel visibility at 80x20 with four conversations
and three project suggestions. Operations are synthetic; no native auth/models.
Independent final review found no further actionable issues. Live plugin loads;
Thurbox 2.75.2 has one generic on_click catalog warning despite semantic commands.
