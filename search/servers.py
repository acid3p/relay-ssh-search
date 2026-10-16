import json
import re
from pathlib import Path, PurePosixPath

from django.conf import settings


class ConfigurationError(Exception):
    pass

def load_servers():
    """Read configuration each request so editing it needs no restart."""
    path = Path(settings.SEARCH_SERVERS_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise ConfigurationError("Cannot read servers.json. Check file permissions and JSON syntax.") from exc
    if not isinstance(data, list):
        raise ConfigurationError("servers.json must contain a JSON array of servers.")
    seen = set()
    servers = []
    for index, entry in enumerate(data, 1):
        prefix = f"Server {index} in servers.json"
        if not isinstance(entry, dict):
            raise ConfigurationError(f"{prefix} must be an object.")
        server = dict(entry)
        for field in ("id", "label", "host", "username", "root"):
            value = server.get(field)
            if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ConfigurationError(f"{prefix}: {field} must be a nonempty string without control characters.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", server["id"]) or server["id"] in seen:
            raise ConfigurationError(f"{prefix}: id must be unique and use letters, digits, hyphens or underscores.")
        root = PurePosixPath(server["root"])
        if not root.is_absolute() or ".." in root.parts:
            raise ConfigurationError(f"{prefix}: root must be an absolute Unix path without '..'.")
        server.setdefault("port", 22)
        if type(server["port"]) is not int or not 1 <= server["port"] <= 65535:
            raise ConfigurationError(f"{prefix}: port must be an integer from 1 to 65535.")
        for field in ("key_filename", "known_hosts", "password_env", "passphrase_env"):
            if field in server and (not isinstance(server[field], str) or not server[field].strip()
                                    or any(ord(c) < 32 for c in server[field])):
                raise ConfigurationError(f"{prefix}: {field} must be a nonempty string without control characters.")
        seen.add(server["id"])
        servers.append(server)
    return servers
