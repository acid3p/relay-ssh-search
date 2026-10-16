# Relay — SSH file search

A small Django app for choosing a server and searching filenames with **fd** or file contents with **ripgrep**, over SSH. It has literal/regex matching, case sensitivity, hidden-file inclusion, line numbers, escaped output, bounded results and useful error messages. It requires no database, frontend build or cloud service.

## Run on this computer

The project virtual environment and dependencies are already installed:

```powershell
cd 'D:\Work\Django Project'
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open <http://127.0.0.1:8000/>. Alternatively run `powershell -ExecutionPolicy Bypass -File .\start.ps1`. Stop with Ctrl+C.

To reinstall on another computer with Python 3.10 or newer:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

`requirements.txt` permits current Django 5.2 security patches and supported Paramiko versions; `requirements.lock.txt` records the versions verified when this project was created. No `migrate` command is needed.

## Add your servers

Edit `servers.json` (initially `[]`). Copy the examples if helpful:

```powershell
Copy-Item .\servers.example.json .\servers.json
notepad .\servers.json
```

Replace the example host/user/root/key with your real values. Do not leave the example servers configured. Add as many entries as needed; separate entries can use different roots on the same host. Changes appear on page reload without restarting Django.

| Field | Meaning |
| --- | --- |
| `id` | Unique identifier containing letters, digits, `_` or `-`. |
| `label` | Name displayed in the server selector. |
| `host` | SSH hostname or IP address. An actual host is required; OpenSSH config aliases, ProxyJump and ProxyCommand are not read. |
| `port` | SSH port; defaults to 22. |
| `username` | Remote SSH account. Prefer a dedicated account with read permissions for your search directory. |
| `root` | Absolute Unix search directory, such as `/srv/app`. No `~` expansion or `..`. The browser cannot override it. |
| `key_filename` | Optional local private key path. `~/.ssh/id_ed25519` works on Windows. Omit it to use the SSH agent or discoverable keys. Use forward slashes or doubled backslashes in JSON Windows paths. |
| `known_hosts` | Optional local host-key file. Defaults to `~/.ssh/known_hosts`. Nonstandard ports require `[hostname]:port` entries. |
| `password_env` | Optional name of an environment variable holding an SSH password. |
| `passphrase_env` | Optional name of an environment variable holding an encrypted key's passphrase. |

Passwords and passphrases never belong in JSON or the webpage. For password authentication, omit `key_filename`, add `"password_env": "SEARCH_SSH_PASSWORD"` and set that variable before starting Django. For encrypted keys use `"passphrase_env": "SEARCH_KEY_PASSPHRASE"`. PowerShell can collect the secret without placing it in command history:

```powershell
$sshSecret = Read-Host 'SSH password' -AsSecureString
$env:SEARCH_SSH_PASSWORD = [System.Net.NetworkCredential]::new('', $sshSecret).Password
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Environment variables must exist in the process starting Django; restart it after changing them. The same pattern works for `SEARCH_KEY_PASSPHRASE`. An SSH agent is preferred when available.

## Trust the SSH host

Verify the host-key fingerprint through a trusted source, then connect once using OpenSSH on the same Windows account running Django:

```powershell
ssh -p 22 your-ssh-user@your-server.example.com
```

Accept only the verified key, then exit the shell. Paramiko rejects unknown or changed host keys. If you use `known_hosts`, put the verified host entry in that file. Don't disable verification to fix a connection error.

## Install remote search tools

The remote host must provide a POSIX shell, fd (or Debian's `fdfind`), ripgrep (`rg`), and GNU `timeout` in the noninteractive SSH PATH.

Ubuntu / Debian, **on the remote server**:

```sh
sudo apt-get update
sudo apt-get install fd-find ripgrep coreutils
```

Fedora:

```sh
sudo dnf install fd-find ripgrep coreutils
```

The app automatically detects `fd` or `fdfind`. Check from the client:

```powershell
ssh your-ssh-user@your-server.example.com 'command -v fd || command -v fdfind; command -v rg; command -v timeout'
```

macOS/BSD hosts need GNU `timeout` exposed under the name `timeout` in their noninteractive PATH. Windows SSH servers with PowerShell/cmd remote shells are not supported by the POSIX command builder.

## Search behavior

- Choose a server, select **File contents** or **Filenames**, enter a query and press **Search server**.
- Queries match literal substrings by default; enable **Regular expression** for regex syntax supported by the selected remote tool. Filenames mode matches the filename, not the entire parent path.
- Case is ignored unless **Case sensitive** is checked. Hidden files are excluded unless enabled. Both tools still respect their normal ignore rules (`.gitignore`, `.ignore`, etc.), even when hidden files are enabled. Binary contents are not normally searched; symlinks are not followed by default.
- Contents results show one row per matching line. Filenames mode lists regular files. Text previews longer than 2,000 characters are shortened. Results are plain text; remote content cannot execute HTML in the page.
- Result limit: 1–500 rows, default 100. SSH stdout is capped at 2 MiB and stderr at 8 KiB; a partial-results notice appears if output or row limits are reached. Results are not sorted. Narrow your query or configure a smaller root to find more.
- GNU timeout stops the remote command after 20 seconds, with a forced kill two seconds later. Connection/authentication phases have separate 8 second timeouts; the local command-reading deadline is 25 seconds. Closing an output-limited channel stops reading immediately; the remote timeout bounds any remaining process lifetime.
- No searches are executed by GET requests. Search content is submitted by POST with CSRF protection, and result pages use `Cache-Control: no-store`. Search history and results are not saved by the app.

## Tests and configuration

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
```

Tests cover configuration, validation, shell quoting, limits, output parsing, SSH errors/cleanup, CSRF and HTML escaping. SSH unit tests isolate the external network boundary; a real server connection requires your configuration and credentials.

Optional environment variables: `SEARCH_SERVERS_FILE` (absolute path to another server config), `DJANGO_DEBUG` (`1` by default for local development), `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (comma-separated; defaults to loopback names). No `.env` auto-loading is included.

This is a **local tool for a trusted operator**: it has no web login and should stay bound to `127.0.0.1`. To share it, first add authentication/authorization, use HTTPS and a production WSGI/ASGI server, set a persistent secret key, turn debug off, and configure allowed hosts. Every user of a shared instance would otherwise inherit the configured SSH account's access. The configured root controls search scope; use remote OS permissions for security isolation.

## References

- [Django project documentation](https://docs.djangoproject.com/en/5.2/intro/tutorial01/)
- [Paramiko SSH client and host-key policy](https://docs.paramiko.org/en/stable/api/client.html)
- [fd documentation](https://github.com/sharkdp/fd)
- [ripgrep](https://github.com/BurntSushi/ripgrep)
