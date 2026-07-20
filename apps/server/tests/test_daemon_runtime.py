from __future__ import annotations

import os
from types import SimpleNamespace

import mission_control_daemon as daemon


def _windows_os_error(winerror: int, message: str) -> OSError:
    exc = OSError(22, message)
    exc.winerror = winerror
    return exc


def test_configure_asyncio_runtime_enables_selector_policy_on_windows(monkeypatch) -> None:
    class FakeIocpProactor:
        def accept(self, *args, **kwargs):
            return None

    class FakePipeTransport:
        def _call_connection_lost(self, exc):
            return None

    class FakeBaseLoop:
        def _start_serving(self, *args, **kwargs):
            return None

    fake_asyncio = SimpleNamespace(
        proactor_events=SimpleNamespace(BaseProactorEventLoop=FakeBaseLoop),
        exceptions=SimpleNamespace(CancelledError=RuntimeError),
        tasks=SimpleNamespace(ensure_future=lambda coro, loop=None: None),
        trsock=SimpleNamespace(TransportSocket=lambda sock: sock),
        windows_events=SimpleNamespace(
            IocpProactor=FakeIocpProactor,
            _overlapped=SimpleNamespace(Overlapped=lambda null: None, SO_UPDATE_ACCEPT_CONTEXT=1),
            NULL=0,
        ),
    )
    fake_asyncio.proactor_events._ProactorBasePipeTransport = FakePipeTransport

    monkeypatch.setattr(daemon, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(daemon, "asyncio", fake_asyncio)

    original = FakeBaseLoop._start_serving
    original_accept = FakeIocpProactor.accept
    original_connection_lost = FakePipeTransport._call_connection_lost

    assert daemon.configure_asyncio_runtime() is True
    assert getattr(FakeBaseLoop, "_mission_control_accept_patch", False) is True
    assert FakeBaseLoop._start_serving is not original
    assert FakeBaseLoop._mission_control_original_start_serving is original
    assert FakeIocpProactor.accept is not original_accept
    assert FakePipeTransport._call_connection_lost is not original_connection_lost


def test_windows_accept_patch_enabled_defaults_on_for_windows(monkeypatch) -> None:
    monkeypatch.setattr(daemon, "os", SimpleNamespace(name="nt", environ=os.environ))
    monkeypatch.delenv("MISSION_CONTROL_ENABLE_WINDOWS_ACCEPT_PATCH", raising=False)
    assert daemon.windows_accept_patch_enabled() is True

    monkeypatch.setenv("MISSION_CONTROL_ENABLE_WINDOWS_ACCEPT_PATCH", "1")
    assert daemon.windows_accept_patch_enabled() is True

    monkeypatch.setenv("MISSION_CONTROL_ENABLE_WINDOWS_ACCEPT_PATCH", "true")
    assert daemon.windows_accept_patch_enabled() is True


def test_windows_accept_patch_enabled_can_be_disabled_explicitly(monkeypatch) -> None:
    monkeypatch.setattr(daemon, "os", SimpleNamespace(name="nt", environ=os.environ))
    monkeypatch.setenv("MISSION_CONTROL_ENABLE_WINDOWS_ACCEPT_PATCH", "0")
    assert daemon.windows_accept_patch_enabled() is False

    monkeypatch.setenv("MISSION_CONTROL_ENABLE_WINDOWS_ACCEPT_PATCH", "off")
    assert daemon.windows_accept_patch_enabled() is False


def test_configure_asyncio_runtime_noops_when_accept_patch_already_active(monkeypatch) -> None:
    class FakeBaseLoop:
        _mission_control_accept_patch = True

        def _start_serving(self, *args, **kwargs):
            return None

    fake_asyncio = SimpleNamespace(
        proactor_events=SimpleNamespace(BaseProactorEventLoop=FakeBaseLoop),
        exceptions=SimpleNamespace(CancelledError=RuntimeError),
        tasks=SimpleNamespace(ensure_future=lambda coro, loop=None: None),
        trsock=SimpleNamespace(TransportSocket=lambda sock: sock),
        windows_events=SimpleNamespace(
            IocpProactor=object,
            _overlapped=SimpleNamespace(Overlapped=lambda null: None, SO_UPDATE_ACCEPT_CONTEXT=1),
            NULL=0,
        ),
    )
    fake_asyncio.proactor_events._ProactorBasePipeTransport = object

    monkeypatch.setattr(daemon, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(daemon, "asyncio", fake_asyncio)

    assert daemon.configure_asyncio_runtime() is False


def test_patched_accept_path_retries_transient_winerror_64(monkeypatch) -> None:
    class FakeIocpProactor:
        def accept(self, *args, **kwargs):
            return None

    class FakePipeTransport:
        def _call_connection_lost(self, exc):
            return None

    class FakeBaseLoop:
        def _start_serving(self, *args, **kwargs):
            return None

    fake_asyncio = SimpleNamespace(
        proactor_events=SimpleNamespace(BaseProactorEventLoop=FakeBaseLoop),
        exceptions=SimpleNamespace(CancelledError=RuntimeError),
        tasks=SimpleNamespace(ensure_future=lambda coro, loop=None: None),
        trsock=SimpleNamespace(TransportSocket=lambda sock: sock),
        windows_events=SimpleNamespace(
            IocpProactor=FakeIocpProactor,
            _overlapped=SimpleNamespace(Overlapped=lambda null: None, SO_UPDATE_ACCEPT_CONTEXT=1),
            NULL=0,
        ),
    )
    fake_asyncio.proactor_events._ProactorBasePipeTransport = FakePipeTransport

    monkeypatch.setattr(daemon, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(daemon, "asyncio", fake_asyncio)
    daemon.configure_asyncio_runtime()

    class FakeFuture:
        def __init__(self, *, result=None, exc=None) -> None:
            self._result = result
            self._exc = exc
            self.callback = None

        def result(self):
            if self._exc is not None:
                raise self._exc
            return self._result

        def add_done_callback(self, callback):
            self.callback = callback

    class FakeSocket:
        def __init__(self) -> None:
            self.closed = False

        def fileno(self):
            return 101

        def close(self):
            self.closed = True

    class FakeLoop(FakeBaseLoop):
        def __init__(self) -> None:
            self._debug = False
            self._accept_futures = {}
            self._scheduled = []
            self._socket_transports = []
            self._proactor = SimpleNamespace(accept=self._accept)

        def call_soon(self, callback):
            self._scheduled.append(callback)

        def is_closed(self):
            return False

        def call_exception_handler(self, context):
            raise AssertionError(f"exception handler should not run for transient accept errors: {context}")

        def _make_socket_transport(self, conn, protocol, extra=None, server=None):
            self._socket_transports.append((conn, protocol, extra, server))

        def _accept(self, sock):
            future = self._accept_queue.pop(0)
            return future

    transient_exc = _windows_os_error(64, "The specified network name is no longer available")
    first_future = FakeFuture(exc=transient_exc)
    retry_future = FakeFuture(result=("conn", ("127.0.0.1", 8010)))
    post_success_future = FakeFuture()
    loop = FakeLoop()
    loop._accept_queue = [first_future, retry_future, post_success_future]
    sock = FakeSocket()
    protocol_factory = lambda: "protocol"

    loop._start_serving(protocol_factory, sock, server="server")

    assert len(loop._scheduled) == 1
    callback = loop._scheduled[0]
    callback()
    assert loop._accept_futures[sock.fileno()] is first_future
    assert first_future.callback is callback

    callback(first_future)
    assert loop._accept_futures[sock.fileno()] is retry_future
    assert retry_future.callback is callback
    assert sock.closed is False

    callback(retry_future)
    assert loop._socket_transports == [("conn", "protocol", {"peername": ("127.0.0.1", 8010)}, "server")]
    assert loop._accept_futures[sock.fileno()] is post_success_future


def test_configure_asyncio_runtime_noops_outside_windows(monkeypatch) -> None:
    fake_asyncio = SimpleNamespace()
    monkeypatch.setattr(daemon, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(daemon, "asyncio", fake_asyncio)

    assert daemon.configure_asyncio_runtime() is False


def test_await_accept_future_swallow_transient_winerror_and_close_conn() -> None:
    class FakeFuture:
        def __await__(self):
            raise _windows_os_error(64, "The specified network name is no longer available")
            yield

    class FakeConn:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    conn = FakeConn()

    async def run() -> None:
        await daemon._await_accept_future(FakeFuture(), conn, RuntimeError)

    import asyncio

    asyncio.run(run())
    assert conn.closed is True


def test_shutdown_transport_socket_ignores_connection_reset() -> None:
    class FakeSocket:
        def fileno(self) -> int:
            return 1

        def shutdown(self, _how) -> None:
            raise _windows_os_error(10054, "An existing connection was forcibly closed by the remote host")

    daemon._shutdown_transport_socket(FakeSocket())
