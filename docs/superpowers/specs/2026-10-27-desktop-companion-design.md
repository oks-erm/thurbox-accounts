# Desktop account companion

The user delegated the approach: whatever makes account switching possible and
not too clumsy. Use a small native Mac window over the existing account backend.
This is a companion for guarded Claude Code sessions, not an extension injected
into the proprietary Claude Desktop app. Official Desktop resume does not provide
our supervisor lease or certify cross-account behavior, so do not route managed
history there.

SwiftUI/AppKit, macOS 13+, no package dependencies. One window shows accounts,
account-scoped conversations, live native console output, an explicit Send
composer, native prompt navigation keys and a named Switch to account button.
The user can add/login profiles, check login, choose a project, create sessions,
verify compatibility and enable selected sharing. Browser/SSO runs through the
existing native CLI in Terminal. No credential files or app cookies are read.

Python desktop.py is an adapter over Accounts/Shared/public Thurbox CLI, never a
second authentication/session implementation. List only local sessions owned by
this extension. Send/key operations require current active ownership and refuse
stopped/stale/unknown foreground state. Display native confirmations; do not auto
answer them. No model request on app startup, refresh or switch. Only explicit
Send or the clearly confirmed paid verification uses models. Shared enrollment
requires an alert naming the ordered accounts and context exposure. Existing
native proof and busy/unknown/orphan refusals remain unchanged.

Keep process work off the UI thread; bound subprocess time/output, avoid shell
interpolation and overlapping UI mutations. Refresh lightweight metadata/output,
not native auth/fingerprints. Preserve errors visibly. Ship app build/install as
an explicit desktop-install command, installing under ~/Applications without
replacing unrelated app bundles. Bundle a pinned interpreter/launcher invocation
configuration (paths only, no credentials); no network server or open local port.

Validate adapter authorization/array API normalization, stale ownership, literal
input, setup gates and build ownership. Compile native app, exercise its bridge
against a synthetic backend and inspect the real UI with empty real profiles.
Native Enterprise authentication remains unverified and gated until user login.
