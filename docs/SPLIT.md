# Standalone Accounts Split

Extract the existing account service, pane and tests; retain only the generic
helpers they use. The repository, extension and CLI are `thurbox-accounts`.
Preserve the old private state directory and UI ownership hashes without moving
or inspecting credentials. Remove accounts from the workflow extension, leaving
a short link to this repository. Validate both suites, isolated payload execution,
plugin loading and real tmux smoke. Create a private repository, push both changes
and inspect CI. Real Enterprise SSO remains user-controlled and unverified.
