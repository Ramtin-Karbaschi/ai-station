#!/usr/bin/env python3
from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from apps.tool_gateway.app.security import UnsafeUrlError, resolve_public_addresses, validate_url_syntax


class ToolGatewaySsrfTests(unittest.TestCase):
    def test_rejects_credentials_and_non_http_schemes(self) -> None:
        for url in ("file:///etc/passwd", "http://user:pass@example.com/"):
            with self.assertRaises(UnsafeUrlError):
                validate_url_syntax(url)

    def test_rejects_nonstandard_ports(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_url_syntax("https://example.com:8443/file")

    def test_rejects_private_and_loopback_dns_answers(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=answers):
            with self.assertRaises(UnsafeUrlError):
                resolve_public_addresses("attacker.example")

    def test_accepts_only_global_dns_answers(self) -> None:
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        with patch("socket.getaddrinfo", return_value=answers):
            self.assertEqual(resolve_public_addresses("example.com"), {"93.184.216.34"})


if __name__ == "__main__":
    unittest.main()
