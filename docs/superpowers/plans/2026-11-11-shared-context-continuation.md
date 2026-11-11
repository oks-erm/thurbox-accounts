# Shared context continuation implementation plan

**Goal:** Continue a selected conversation under another logged-in account without
requiring native cross-account resume, source model allowance, or source shutdown.

**Architecture:** Keep logins isolated. Store private, bounded transcript snapshots
and a readable handoff in an account-independent context space. New named-account
sessions receive a one-time initial prompt to read that space. Persist lineage so
later continuations retain access to earlier snapshots.

The user already requested implementation and opted out of repeated approval
questions. Implement inline in the existing checkout, preserving pending fixes.

- [x] Add `continuation.py`: resolve selected local Claude history without source
  auth, snapshot only that transcript, prepare recent-message context and lineage,
  reserve a destination, and deduplicate retries using source-content identity.
- [x] Add a guarded one-shot bootstrap: validate owner, target identity, fresh
  native UUID and artifact hashes. Pass the initial prompt only once; persistent
  session arguments must not replay it on restart.
- [x] Expose `continue-context --session REF --to PROFILE --consent`; return the
  new session ID and handoff location. Keep native shared switching available via
  its existing CLI rather than silently falling back after an ambiguous launch.
- [x] Make the account chooser use continuation, including ordinary and failed
  sources. Freeze displayed target identity/source UUID before a destination click.
  State clearly that a new conversation reads saved context and that the source
  remains untouched. Follow the destination from its receipt.
- [x] Test source quota/stale workers, missing history, lineage, identity races,
  one-shot delivery, launch failures/retries, and no credential copying. Run full
  Python suite, Lua chooser smoke, compile and packaging/manifest checks.

**Review focus:** no model request to the source; no credentials/shared config;
no source mutation/stop; no empty fallback; no prompt replay; no duplicate target
after uncertain creation; no lost ancestral context on a later continuation.
