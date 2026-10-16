import base64
import json
import shlex
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import paramiko
from django.test import Client, SimpleTestCase, override_settings

from .forms import SearchForm
from .remote import SearchError, build_command, parse_output, read_channel, search_remote
from .servers import ConfigurationError, load_servers

SERVER = {"id": "dev", "label": "Development", "host": "example.test", "port": 22,
          "username": "reader", "root": "/srv/app"}
DATA = {"server": "dev", "mode": "text", "query": "hello", "regex": False,
        "case_sensitive": False, "hidden": False, "limit": 100}


def match(path="/srv/app/a.py", text="hello world\n", line=12):
    return json.dumps({"type": "match", "data": {"path": {"text": path},
        "lines": {"text": text}, "line_number": line}}).encode() + b"\n"


class ConfigurationTests(SimpleTestCase):
    def load(self, value):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "servers.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with override_settings(SEARCH_SERVERS_FILE=path):
                return load_servers()

    def test_missing_file_is_empty_first_run(self):
        with override_settings(SEARCH_SERVERS_FILE=Path("missing-test-config.json")):
            self.assertEqual(load_servers(), [])

    def test_server_defaults_and_configuration(self):
        server = {k: v for k, v in SERVER.items() if k != "port"}
        self.assertEqual(self.load([server])[0]["port"], 22)

    def test_rejects_duplicate_identifiers(self):
        with self.assertRaises(ConfigurationError):
            self.load([SERVER, SERVER])

    def test_rejects_invalid_configuration(self):
        for key, value in [("root", "relative"), ("root", "/srv/../etc"),
                           ("port", 0), ("port", True), ("host", ""),
                           ("id", "bad id"), ("username", "\x00")]:
            with self.subTest(key=key, value=value), self.assertRaises(ConfigurationError):
                self.load([{**SERVER, key: value}])

    def test_malformed_json_is_actionable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "servers.json"
            path.write_text("broken", encoding="utf-8")
            with override_settings(SEARCH_SERVERS_FILE=path), self.assertRaises(ConfigurationError):
                load_servers()


class FormTests(SimpleTestCase):
    def test_valid_submission(self):
        form = SearchForm(DATA, servers=[SERVER])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data.get("query"), "hello")

    def test_rejects_tampered_server_mode_limit_and_control_characters(self):
        for values in [{"server": "other"}, {"mode": "shell"}, {"limit": "501"},
                       {"limit": "0"}, {"query": "  "}, {"query": "a\x00b"},
                       {"query": "a\nb"}]:
            with self.subTest(values=values):
                self.assertFalse(SearchForm({**DATA, **values}, servers=[SERVER]).is_valid())


class CommandTests(SimpleTestCase):
    def test_text_is_literal_and_option_safe(self):
        command = build_command(SERVER, {**DATA, "query": "--pre=touch /tmp/pwn"})
        args = shlex.split(command)
        self.assertIn("--fixed-strings", args)
        self.assertIn("--json", args)
        self.assertIn("--no-config", args)
        self.assertEqual(args[-3:], ["--", "--pre=touch /tmp/pwn", "/srv/app"])

    def test_quotes_shell_metacharacters_and_root(self):
        query = "x'; $(touch /tmp/pwn) `id`"
        command = build_command({**SERVER, "root": "/srv/my app"}, {**DATA, "query": query})
        self.assertEqual(shlex.split(command)[-2:], [query, "/srv/my app"])

    def test_regex_case_and_hidden_options(self):
        args = shlex.split(build_command(SERVER, {**DATA, "regex": True,
                              "case_sensitive": True, "hidden": True}))
        self.assertNotIn("--fixed-strings", args)
        self.assertIn("--case-sensitive", args)
        self.assertIn("--hidden", args)

    def test_file_search_supports_debian_fdfind(self):
        command = build_command(SERVER, {**DATA, "mode": "files"})
        self.assertIn("fdfind", command)
        self.assertIn("--print0", command)
        self.assertIn("--type", command)
        self.assertIn("timeout", command)


class ParsingTests(SimpleTestCase):
    def test_text_preserves_colons_and_newlines_in_paths(self):
        result = parse_output("text", match("/srv/a:b\nc.py"), 100)
        self.assertEqual(result["rows"], [{"path": "/srv/a:b\nc.py", "line": 12, "text": "hello world"}])

    def test_binary_json_fields_are_decoded(self):
        payload = {"type": "match", "data": {"path": {"bytes": base64.b64encode(b"/srv/a").decode()},
                   "lines": {"bytes": base64.b64encode(b"hi\xff\n").decode()}, "line_number": 1}}
        result = parse_output("text", json.dumps(payload).encode() + b"\n", 2)
        self.assertEqual(result["rows"][0]["text"], "hi\ufffd")

    def test_files_use_null_delimiters(self):
        rows = parse_output("files", b"/srv/a\nb\x00/srv/c\x00", 100)["rows"]
        self.assertEqual([row["path"] for row in rows], ["/srv/a\nb", "/srv/c"])

    def test_result_limit_is_reported(self):
        result = parse_output("text", match() * 3, 2)
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(result["truncated"])

    def test_partial_output_drops_incomplete_record(self):
        result = parse_output("text", match() + b'{"type":', 100, truncated=True)
        self.assertEqual(len(result["rows"]), 1)
        result = parse_output("files", b"/srv/a\x00/srv/par", 100, truncated=True)
        self.assertEqual(len(result["rows"]), 1)

    def test_invalid_protocol_reports_error(self):
        with self.assertRaises(SearchError):
            parse_output("text", b"not-json\n", 100)


class ChannelTests(SimpleTestCase):
    def channel(self, stdout=b"", stderr=b"", status=0):
        channel = MagicMock()
        channel.recv_ready.side_effect = [bool(stdout), False, False]
        channel.recv.return_value = stdout
        channel.recv_stderr_ready.side_effect = [bool(stderr), False, False]
        channel.recv_stderr.return_value = stderr
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.return_value = status
        return channel

    def test_reads_output_and_error_without_deadlock(self):
        result = read_channel(self.channel(b"result", b"warning"), time.monotonic() + 2)
        self.assertEqual(result, (b"result", b"warning", 0, False))

    def test_caps_output_and_closes_channel(self):
        channel = self.channel(b"x" * 100)
        result = read_channel(channel, time.monotonic() + 2, max_bytes=20)
        self.assertEqual(len(result[0]), 20)
        self.assertTrue(result[3])
        channel.close.assert_called()

    def test_deadline_stops_stalled_search(self):
        with self.assertRaises(SearchError):
            read_channel(self.channel(), time.monotonic() - 1)


class SSHTests(SimpleTestCase):
    @patch("search.remote.paramiko.SSHClient")
    @patch("search.remote.read_channel", return_value=(match(), b"", 0, False))
    def test_connects_with_verified_keys_and_closes(self, reader, factory):
        client = factory.return_value
        client.exec_command.return_value = (MagicMock(), MagicMock(), MagicMock())
        result = search_remote(SERVER, DATA)
        self.assertEqual(result["rows"][0]["line"], 12)
        self.assertIsInstance(client.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy)
        self.assertEqual(client.connect.call_args.kwargs["hostname"], "example.test")
        client.close.assert_called_once()

    @patch("search.remote.paramiko.SSHClient")
    @patch("search.remote.read_channel", return_value=(b"", b"", 1, False))
    def test_ripgrep_no_matches_is_success(self, reader, factory):
        factory.return_value.exec_command.return_value = (MagicMock(), MagicMock(), MagicMock())
        self.assertEqual(search_remote(SERVER, DATA)["rows"], [])

    @patch("search.remote.paramiko.SSHClient")
    @patch("search.remote.read_channel", return_value=(b"", b"rg missing", 127, False))
    def test_remote_failure_is_actionable(self, reader, factory):
        factory.return_value.exec_command.return_value = (MagicMock(), MagicMock(), MagicMock())
        with self.assertRaisesMessage(SearchError, "rg missing"):
            search_remote(SERVER, DATA)
        factory.return_value.close.assert_called_once()

    @patch("search.remote.paramiko.SSHClient")
    def test_authentication_failure_closes_connection(self, factory):
        factory.return_value.connect.side_effect = paramiko.AuthenticationException("denied")
        with self.assertRaisesMessage(SearchError, "authentication"):
            search_remote(SERVER, DATA)
        factory.return_value.close.assert_called_once()


@patch("search.views.load_servers", return_value=[SERVER])
class PageTests(SimpleTestCase):
    def test_page_has_server_and_search_controls(self, servers):
        response = self.client.get("/")
        self.assertContains(response, "Development")
        self.assertContains(response, 'name="query"')
        self.assertContains(response, 'name="server"')

    @patch("search.views.search_remote", return_value={"rows": [{"path": "/srv/a.py", "line": 3,
            "text": "<script>alert(1)</script>"}], "truncated": False, "warning": "", "elapsed": 0.1})
    def test_valid_search_displays_escaped_result(self, search, servers):
        response = self.client.post("/", DATA)
        self.assertContains(response, "/srv/a.py")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    @patch("search.views.search_remote")
    def test_invalid_server_never_connects(self, search, servers):
        response = self.client.post("/", {**DATA, "server": "evil"})
        self.assertContains(response, "Select a valid choice")
        search.assert_not_called()

    @patch("search.views.search_remote", side_effect=SearchError("Connection refused"))
    def test_connection_error_renders_in_page(self, search, servers):
        self.assertContains(self.client.post("/", DATA), "Connection refused")

    def test_csrf_is_enforced(self, servers):
        self.assertEqual(Client(enforce_csrf_checks=True).post("/", DATA).status_code, 403)

    def test_get_never_starts_search(self, servers):
        with patch("search.views.search_remote") as search:
            self.client.get("/", DATA)
            search.assert_not_called()


class FirstRunTests(SimpleTestCase):
    @patch("search.views.load_servers", return_value=[])
    def test_empty_configuration_has_setup_instructions(self, servers):
        self.assertContains(self.client.get("/"), "servers.json")

    @patch("search.views.load_servers", side_effect=ConfigurationError("Invalid servers.json"))
    def test_bad_configuration_renders_help(self, servers):
        self.assertContains(self.client.get("/"), "Invalid servers.json")
