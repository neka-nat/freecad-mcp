"""Capture Python stdout on the executing thread without collecting other threads."""

from collections.abc import Iterator
from contextlib import contextmanager
import sys
import threading
from typing import Any, TextIO


_install_lock = threading.Lock()


class _ThreadStdoutRouter:
    """Proxy the active thread's capture, or the original console stream."""

    def __init__(self, wrapped: TextIO | None) -> None:
        self.wrapped = wrapped
        self.captures = 0  # protected by _install_lock
        self.local = threading.local()

    def _target(self) -> TextIO | None:
        return getattr(self.local, "target", self.wrapped)

    def write(self, text: str) -> int | None:
        target = self._target()
        return len(text) if target is None else target.write(text)

    def flush(self) -> None:
        target = self._target()
        if target is not None:
            target.flush()

    def __getattr__(self, name: str) -> Any:
        # Keep the console's stream API (encoding, isatty, fileno, writelines,
        # etc.) for noncapturing threads instead of TextIOBase's dummy methods.
        return getattr(self._target(), name)

    @contextmanager
    def capture(self, buffer: TextIO) -> Iterator[None]:
        previous = self._target()
        self.local.target = buffer
        try:
            yield
        finally:
            self.local.target = previous


@contextmanager
def capture_stdout(buffer: TextIO) -> Iterator[None]:
    """Capture this thread only, restoring stdout after the last active capture.

    Threads spawned by a script retain normal console output. This routes
    Python stdout writes; it does not intercept native file-descriptor writes.
    """
    with _install_lock:
        router = sys.stdout
        if not isinstance(router, _ThreadStdoutRouter):
            router = _ThreadStdoutRouter(router)
            sys.stdout = router
        router.captures += 1
    try:
        with router.capture(buffer):
            yield
    finally:
        with _install_lock:
            router.captures -= 1
            if router.captures == 0 and sys.stdout is router:
                # Do not overwrite a replacement installed by another addon.
                sys.stdout = router.wrapped
