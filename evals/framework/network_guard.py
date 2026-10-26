"""Process-local Python socket guard for synchronous offline evaluation.

Not an OS firewall: runners must not launch arbitrary subprocesses or native
provider clients. Keep dependency installation outside this context.
"""

import socket
from contextlib import contextmanager
from threading import RLock

_LOCK = RLock()


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("network access blocked in offline evaluation")


@contextmanager
def offline_network():
    """Block even loopback/DNS and restore exact prior functions on every exit."""
    with _LOCK:
        targets = [(socket.socket, name) for name in ("connect", "connect_ex", "send", "sendall", "sendto", "sendmsg")
                   if hasattr(socket.socket, name)]
        targets += [(socket, name) for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")]
        originals = [(owner, name, getattr(owner, name)) for owner, name in targets]
        try:
            for owner, name, _ in originals:
                setattr(owner, name, _blocked)
            yield
        finally:
            for owner, name, value in reversed(originals):
                setattr(owner, name, value)
