import os
import tempfile
import unittest

import admin_agent


class ParseTests(unittest.TestCase):
    def test_parse_health(self):
        self.assertEqual(admin_agent.parse_health("Up 2 days (healthy)"), "healthy")
        self.assertEqual(admin_agent.parse_health("Up 2 days (unhealthy)"), "unhealthy")
        self.assertEqual(admin_agent.parse_health("Up 2 days (starting)"), "starting")
        self.assertEqual(admin_agent.parse_health("Up 7 seconds (health: starting)"), "starting")
        self.assertEqual(admin_agent.parse_health("Up 2 days"), "")

    def test_format_ports(self):
        ports = [
            {"PrivatePort": 8096, "PublicPort": 8096, "Type": "tcp"},
            {"PrivatePort": 7006, "Type": "tcp"},
            {"PrivatePort": 6881, "PublicPort": 6881, "Type": "udp"},
        ]
        self.assertEqual(
            admin_agent.format_ports(ports),
            ["6881->6881/udp", "7006/tcp", "8096->8096/tcp"],
        )

    def test_display_name(self):
        self.assertEqual(admin_agent.display_name("torrent-indexer"), "Torrent Indexer")
        self.assertEqual(admin_agent.display_name("novo-servico"), "Novo Servico")


class PasswordTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("ADMIN_PASSWORD", None)
        admin_agent.clear_failures("127.0.0.1")

    def test_env_password(self):
        os.environ["ADMIN_PASSWORD"] = "segredo"
        self.assertEqual(admin_agent.admin_password(), "segredo")

    def test_file_password(self):
        os.environ.pop("ADMIN_PASSWORD", None)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write("do-arquivo\n")
            path = handle.name
        old = admin_agent.PASSWORD_FILE
        admin_agent.PASSWORD_FILE = path
        try:
            self.assertEqual(admin_agent.admin_password(), "do-arquivo")
        finally:
            admin_agent.PASSWORD_FILE = old
            os.unlink(path)

    def test_rate_limit(self):
        admin_agent.clear_failures("10.0.0.1")
        for _ in range(admin_agent._FAIL_LIMIT):
            self.assertTrue(admin_agent.rate_ok("10.0.0.1"))
            admin_agent.record_failure("10.0.0.1")
        self.assertFalse(admin_agent.rate_ok("10.0.0.1"))
        admin_agent.clear_failures("10.0.0.1")
        self.assertTrue(admin_agent.rate_ok("10.0.0.1"))


if __name__ == "__main__":
    unittest.main()
