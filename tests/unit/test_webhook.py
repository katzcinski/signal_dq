"""Tests for SSRF-safe webhook caller (WS5-3 / S6)."""
from unittest.mock import patch

import pytest

from services.api.webhook import _is_private_host, _host_in_allowlist, fire_webhook


class TestPrivateHostDetection:
    def test_loopback_is_private(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            assert _is_private_host("localhost") is True

    def test_rfc1918_10_is_private(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 0))]):
            assert _is_private_host("internal.corp") is True

    def test_rfc1918_172_is_private(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("172.20.0.1", 0))]):
            assert _is_private_host("docker.internal") is True

    def test_rfc1918_192_is_private(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("192.168.1.1", 0))]):
            assert _is_private_host("router") is True

    def test_public_ip_is_not_private(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("8.8.8.8", 0))]):
            assert _is_private_host("dns.google") is False

    def test_unresolvable_treated_as_private(self):
        with patch("socket.getaddrinfo", side_effect=OSError("no route")):
            assert _is_private_host("nonexistent.invalid") is True


class TestAllowlist:
    def test_exact_match(self):
        assert _host_in_allowlist("hooks.example.com", [r"hooks\.example\.com"]) is True

    def test_wildcard_pattern(self):
        assert _host_in_allowlist("api.example.com", [r".*\.example\.com"]) is True

    def test_not_in_allowlist(self):
        assert _host_in_allowlist("evil.com", [r".*\.example\.com"]) is False

    def test_empty_allowlist(self):
        assert _host_in_allowlist("example.com", []) is False


class TestFireWebhook:
    def test_empty_url_is_noop(self):
        # Should not raise anything
        fire_webhook("", {}, [])

    def test_raises_when_host_not_in_allowlist(self):
        with pytest.raises(ValueError, match="not in WEBHOOK_ALLOWLIST"):
            fire_webhook("https://evil.com/hook", {}, [r".*\.example\.com"])

    def test_raises_when_private_ip(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 0))]):
            with pytest.raises(ValueError, match="private IP"):
                fire_webhook("https://internal.corp/hook", {}, [r".*\.corp"])
