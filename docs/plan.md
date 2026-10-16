# Implementation plan

1. Scaffold Django settings, routes and isolated dependencies. Write tests for configuration, validation, command safety, parsing, connection lifecycle and page behavior; verify red against empty stubs.
2. Implement validated server JSON loading, form controls, quoted fd/rg commands, bounded SSH output collection and safe result parsing. Verify the core tests.
3. Implement POST page with escaped result table, empty/setup/error states and responsive styles. Verify the complete suite and Django checks.
4. Add example configuration, README and PowerShell launcher. Copy reviewed source into the requested folder, freeze installed dependency versions, launch on loopback and inspect the browser if available.

Review focus: shell injection and leading options; malformed config/unknown server IDs; SSH host-key enforcement and cleanup; output/time limits and no-match exit statuses; HTML escaping and CSRF. Use native inline execution. Do not create a repository or make commits in this empty non-Git project.
