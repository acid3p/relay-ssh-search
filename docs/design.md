# SSH Search design — 2026-10-16

Build a local Django webpage for selecting a configured Linux/Unix SSH server and searching filenames with fd/fdfind or contents with ripgrep. The user requests completion in one prompt, so implementation proceeds without intermediate design approvals. This is a new project; the requested folder is empty and is the final destination.

Use Django templates, plain CSS and a small progressive-enhancement script, plus Paramiko. Server definitions live in local servers.json; allow only configured server IDs and fixed absolute search roots. Authentication uses an SSH agent, local key, or environment variable. Reject untrusted host keys. No secrets enter HTML. No database is required. The local app is intended for one trusted operator, binds to loopback and has no login; external deployment requires authentication.

POST with CSRF protection validates mode, nonempty query, options and result limit. All shell arguments are POSIX quoted and use an option terminator. Literal matching is the default, with optional regex, case sensitivity, and hidden files. fd emits NUL-delimited filenames; rg emits JSON preserving unusual paths. GNU timeout limits remote searches, local connection/read deadlines and output caps bound requests. Results are escaped by Django and show filenames, line numbers, contents, count and truncation/errors. Remote symlinks are not followed by default; search roots are scope choices, not a filesystem security boundary.

First run shows setup instructions without fake servers. Include example configuration, PowerShell launcher, installation/run documentation and automated tests. Real SSH verification requires server details and credentials that were not supplied.
