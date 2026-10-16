import base64
import binascii
import json
import os
import shlex
import socket
import time
from pathlib import Path

import paramiko

class SearchError(Exception):
    pass

def build_command(server, data):
    """All variable arguments are quoted; users cannot supply CLI options."""
    if data["mode"] == "files":
        args = ["--type", "f", "--absolute-path", "--print0", "--color", "never"]
    else:
        args = ["--no-config", "--json", "--line-number", "--color", "never"]
    if not data.get("regex"):
        args.append("--fixed-strings")
    args.append("--case-sensitive" if data.get("case_sensitive") else "--ignore-case")
    if data.get("hidden"):
        args.append("--hidden")
    args += ["--", data["query"], server["root"]]
    suffix = shlex.join(args)
    # A remote deadline also stops scanning when the SSH channel is abandoned.
    deadline = "exec timeout --signal=TERM --kill-after=2s 20s"
    if data["mode"] == "files":
        return (f"if command -v fd >/dev/null 2>&1; then {deadline} fd {suffix}; "
                f"elif command -v fdfind >/dev/null 2>&1; then {deadline} fdfind {suffix}; "
                "else printf '%s\\n' 'Install fd (or fdfind) on this server.' >&2; exit 127; fi")
    return f"{deadline} rg {suffix}"

def parse_output(mode, raw, limit, truncated=False):
    rows = []
    if mode == "files":
        # Only complete NUL-terminated names; a cut-off name is never displayed.
        records = raw.split(b"\0")[:-1]
        for record in records[:limit + 1]:
            rows.append({"path": record.decode("utf-8", errors="replace"), "line": None, "text": ""})
    else:
        records = raw.split(b"\n")
        if truncated or not records[-1]:
            records.pop()
        for record in records:
            if not record:
                continue
            try:
                event = json.loads(record)
                if event["type"] != "match":
                    continue
                item = event["data"]
                def decode(field):
                    if "text" in field:
                        return field["text"]
                    return base64.b64decode(field["bytes"], validate=True).decode("utf-8", errors="replace")
                text = decode(item["lines"]).rstrip("\r\n")
                if len(text) > 2000:
                    text = text[:2000] + " … [line shortened]"
                rows.append({"path": decode(item["path"]), "line": item["line_number"], "text": text})
            except (ValueError, KeyError, TypeError, binascii.Error) as exc:
                raise SearchError("Unexpected ripgrep output. Check that rg supports --json and the SSH shell prints no startup banners.") from exc
            if len(rows) > limit:
                break
    return {"rows": rows[:limit], "truncated": truncated or len(rows) > limit}

def read_channel(channel, deadline, max_bytes=2097152):
    """Drain both streams before exit status to avoid SSH window deadlocks."""
    output = bytearray()
    errors = bytearray()
    while True:
        if time.monotonic() >= deadline:
            channel.close()
            raise SearchError("Search timed out. Try a narrower query or a smaller configured search directory.")
        active = False
        if channel.recv_ready():
            chunk = channel.recv(32768)
            active = True
            remaining = max_bytes - len(output)
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                channel.close()
                return bytes(output), bytes(errors), None, True
        if channel.recv_stderr_ready():
            chunk = channel.recv_stderr(32768)
            active = True
            errors.extend(chunk[:max(0, 8192 - len(errors))])
        if not active and channel.exit_status_ready():
            return bytes(output), bytes(errors), channel.recv_exit_status(), False
        if not active:
            time.sleep(0.01)

def search_remote(server, data):
    started = time.monotonic()
    client = paramiko.SSHClient()
    try:
        client.load_system_host_keys()
        known_hosts = Path(server.get("known_hosts", "~/.ssh/known_hosts")).expanduser()
        if known_hosts.is_file():
            client.load_host_keys(str(known_hosts))
        elif server.get("known_hosts"):
            raise SearchError("The configured known_hosts file does not exist.")
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        credentials = {}
        if server.get("key_filename"):
            credentials["key_filename"] = str(Path(server["key_filename"]).expanduser())
        for field, argument in (("password_env", "password"), ("passphrase_env", "passphrase")):
            if server.get(field):
                secret = os.environ.get(server[field])
                if not secret:
                    raise SearchError(f"Set the environment variable named by {field} before starting Django.")
                credentials[argument] = secret
        client.connect(hostname=server["host"], port=server.get("port", 22), username=server["username"],
                       timeout=8, auth_timeout=8, banner_timeout=8, channel_timeout=8,
                       allow_agent=True, look_for_keys=True, **credentials)
        stdin, stdout, stderr = client.exec_command(build_command(server, data), timeout=8, get_pty=False)
        stdin.close()
        raw, errors, status, cut_off = read_channel(stdout.channel, time.monotonic() + 25)
        warning = errors.decode("utf-8", errors="replace").strip()
        if status in (124, 137):
            raise SearchError("Remote search reached the 20 second limit. Use a smaller search directory or a narrower query.")
        accepted = (0, 1) if data["mode"] == "text" else (0,)
        if status is not None and status not in accepted:
            raise SearchError(f"Remote search failed (exit {status}). {warning or 'Check fd, rg and GNU timeout are installed and the directory is readable.'}")
        result = parse_output(data["mode"], raw, data["limit"], truncated=cut_off)
        result.update(warning=warning, elapsed=round(time.monotonic() - started, 2))
        return result
    except paramiko.AuthenticationException as exc:
        raise SearchError("SSH authentication failed. Check the username, SSH agent, key file or password environment variable.") from exc
    except paramiko.BadHostKeyException as exc:
        raise SearchError("SSH host key changed. Verify the server fingerprint before updating known_hosts.") from exc
    except paramiko.SSHException as exc:
        raise SearchError("SSH connection failed. Verify the server host key in known_hosts, SSH settings and network access.") from exc
    except (OSError, socket.timeout) as exc:
        raise SearchError("Cannot connect over SSH or read the key file. Check the host, port, network, file permissions and key passphrase.") from exc
    finally:
        client.close()
