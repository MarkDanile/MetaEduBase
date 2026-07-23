"""Regression tests for the default-deny external network test boundary."""

import socket

import pytest

from tests.conftest import _TEST_DB_PORT, UnmockedExternalNetworkError


def test_unmocked_external_connection_fails_fast() -> None:
    with socket.socket() as client, pytest.raises(
        UnmockedExternalNetworkError,
        match="unmocked external connection blocked",
    ):
        client.connect(("203.0.113.1", 443))


def test_unmocked_external_dns_lookup_fails_fast() -> None:
    with pytest.raises(
        UnmockedExternalNetworkError,
        match="unmocked external DNS lookup blocked",
    ):
        socket.getaddrinfo("example.invalid", 443)


def test_database_port_on_another_host_is_still_blocked() -> None:
    with socket.socket() as client, pytest.raises(
        UnmockedExternalNetworkError,
        match="unmocked external connection blocked",
    ):
        client.connect(("203.0.113.1", _TEST_DB_PORT))
