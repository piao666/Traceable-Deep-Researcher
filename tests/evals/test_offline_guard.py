import socket

import pytest

from evals.framework.network_guard import NetworkBlocked, offline_network


def test_guard_blocks_connection_dns_connect_ex_and_udp_and_restores():
    originals = (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo, socket.socket.sendto)
    with offline_network():
        with socket.socket() as client:
            for action in (lambda: client.connect(("127.0.0.1", 9)),
                           lambda: client.connect_ex(("127.0.0.1", 9)),
                           lambda: socket.getaddrinfo("example.invalid", 443)):
                with pytest.raises(NetworkBlocked):
                    action()
        with socket.socket(type=socket.SOCK_DGRAM) as udp:
            with pytest.raises(NetworkBlocked):
                udp.sendto(b"x", ("127.0.0.1", 9))
    assert originals == (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo, socket.socket.sendto)


def test_nested_guard_cannot_widen_outer_policy():
    original = socket.socket.connect
    with pytest.raises(ValueError):
        with offline_network():
            with offline_network():
                raise ValueError("expected")
    assert socket.socket.connect is original
