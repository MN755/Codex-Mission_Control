from __future__ import annotations

import asyncio
import os
import socket
import struct
import sys
import threading
import time
import traceback

import uvicorn

from config import ensure_runtime_dirs
from daemon_state import (
    daemon_listener_healthy,
    ensure_daemon_token,
    resolve_backend_binding,
    update_daemon_metadata_status,
    write_daemon_metadata,
)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LISTENER_GUARD_INTERVAL_SECONDS = 2.0
LISTENER_GUARD_FAILURE_THRESHOLD = 5
# Keep the listener guard slower than live manager-turn recovery so a temporary
# long-running Codex manager turn can time out and fall back cleanly instead of
# having the daemon kill its own listener first.
LISTENER_GUARD_MIN_OUTAGE_SECONDS = 150.0
TRANSIENT_ACCEPT_WINERRORS = {64}
TRANSIENT_CONNECTION_LOST_WINERRORS = {64, 10054}


def windows_accept_patch_enabled() -> bool:
    environ = getattr(os, "environ", {})
    configured = str(environ.get("MISSION_CONTROL_ENABLE_WINDOWS_ACCEPT_PATCH") or "").strip().lower()
    if configured in {"0", "false", "no", "off"}:
        return False
    if configured in {"1", "true", "yes", "on"}:
        return True
    return os.name == "nt"


def _matches_winerror(exc: BaseException, codes: set[int]) -> bool:
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) in codes


async def _await_accept_future(future, conn, cancelled_error_type) -> None:
    try:
        await future
    except cancelled_error_type:
        conn.close()
        raise
    except OSError as exc:
        conn.close()
        if _matches_winerror(exc, TRANSIENT_ACCEPT_WINERRORS):
            return
        raise


def _shutdown_transport_socket(sock) -> None:
    if not hasattr(sock, "shutdown") or sock.fileno() == -1:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError as exc:
        if not _matches_winerror(exc, TRANSIENT_CONNECTION_LOST_WINERRORS):
            raise


def configure_asyncio_runtime() -> bool:
    if os.name != "nt":
        return False
    proactor_events = getattr(asyncio, "proactor_events", None)
    exceptions_module = getattr(asyncio, "exceptions", None)
    tasks_module = getattr(asyncio, "tasks", None)
    trsock_module = getattr(asyncio, "trsock", None)
    windows_events_module = getattr(asyncio, "windows_events", None)
    base_loop = getattr(proactor_events, "BaseProactorEventLoop", None) if proactor_events is not None else None
    iocp_proactor = getattr(windows_events_module, "IocpProactor", None) if windows_events_module is not None else None
    overlapped_module = getattr(windows_events_module, "_overlapped", None) if windows_events_module is not None else None
    null_handle = getattr(windows_events_module, "NULL", None) if windows_events_module is not None else None
    base_transport = getattr(proactor_events, "_ProactorBasePipeTransport", None) if proactor_events is not None else None
    if (
        base_loop is None
        or base_transport is None
        or exceptions_module is None
        or tasks_module is None
        or trsock_module is None
        or iocp_proactor is None
        or overlapped_module is None
        or null_handle is None
    ):
        return False
    if getattr(base_loop, "_mission_control_accept_patch", False):
        return False

    def patched_start_serving(self, protocol_factory, sock, sslcontext=None, server=None, backlog=100, ssl_handshake_timeout=None):
        def loop(f=None):
            try:
                if f is not None:
                    conn, addr = f.result()
                    if getattr(self, "_debug", False):
                        pass
                    protocol = protocol_factory()
                    if sslcontext is not None:
                        self._make_ssl_transport(
                            conn,
                            protocol,
                            sslcontext,
                            server_side=True,
                            extra={"peername": addr},
                            server=server,
                            ssl_handshake_timeout=ssl_handshake_timeout,
                        )
                    else:
                        self._make_socket_transport(conn, protocol, extra={"peername": addr}, server=server)
                if self.is_closed():
                    return
                f = self._proactor.accept(sock)
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if sock.fileno() != -1 and winerror in TRANSIENT_ACCEPT_WINERRORS and not self.is_closed():
                    retry = self._proactor.accept(sock)
                    self._accept_futures[sock.fileno()] = retry
                    retry.add_done_callback(loop)
                    return
                if sock.fileno() != -1:
                    self.call_exception_handler(
                        {
                            "message": "Accept failed on a socket",
                            "exception": exc,
                            "socket": trsock_module.TransportSocket(sock),
                        }
                    )
                    sock.close()
            except exceptions_module.CancelledError:
                sock.close()
            else:
                self._accept_futures[sock.fileno()] = f
                f.add_done_callback(loop)

        self.call_soon(loop)

    def patched_accept(self, listener):
        self._register_with_iocp(listener)
        conn = self._get_accept_socket(listener.family)
        ov = overlapped_module.Overlapped(null_handle)
        ov.AcceptEx(listener.fileno(), conn.fileno())

        def finish_accept(trans, key, ov):
            ov.getresult()
            buf = struct.pack("@P", listener.fileno())
            conn.setsockopt(socket.SOL_SOCKET, overlapped_module.SO_UPDATE_ACCEPT_CONTEXT, buf)
            conn.settimeout(listener.gettimeout())
            return conn, conn.getpeername()

        future = self._register(ov, listener, finish_accept)
        coro = _await_accept_future(future, conn, exceptions_module.CancelledError)
        tasks_module.ensure_future(coro, loop=self._loop)
        return future

    def patched_call_connection_lost(self, exc):
        if self._called_connection_lost:
            return
        try:
            self._protocol.connection_lost(exc)
        finally:
            sock = self._sock
            if sock is not None:
                _shutdown_transport_socket(sock)
                sock.close()
            self._sock = None
            server = self._server
            if server is not None:
                server._detach()
                self._server = None
            self._called_connection_lost = True

    base_loop._mission_control_original_start_serving = getattr(base_loop, "_start_serving", None)
    base_loop._start_serving = patched_start_serving
    iocp_proactor._mission_control_original_accept = getattr(iocp_proactor, "accept", None)
    iocp_proactor.accept = patched_accept
    base_transport._mission_control_original_call_connection_lost = getattr(base_transport, "_call_connection_lost", None)
    base_transport._call_connection_lost = patched_call_connection_lost
    base_loop._mission_control_accept_patch = True
    return True


def _listener_guard(
    server: uvicorn.Server,
    *,
    host: str,
    port: int,
    stop_event: threading.Event,
    listener_failure_event: threading.Event,
    interval_seconds: float = LISTENER_GUARD_INTERVAL_SECONDS,
    failure_threshold: int = LISTENER_GUARD_FAILURE_THRESHOLD,
    min_outage_seconds: float = LISTENER_GUARD_MIN_OUTAGE_SECONDS,
    healthcheck=daemon_listener_healthy,
    metadata_updater=update_daemon_metadata_status,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
    exit_process=os._exit,
) -> None:
    consecutive_failures = 0
    outage_started_at: float | None = None
    failure_message = (
        f"Mission Control daemon listener guard lost localhost health at {host}:{port} "
        f"for at least {min_outage_seconds:.0f}s across {failure_threshold} consecutive checks."
    )
    while not stop_event.is_set():
        if getattr(server, "should_exit", False):
            return
        if not getattr(server, "started", False):
            sleep_fn(interval_seconds)
            continue
        if healthcheck(host, port):
            consecutive_failures = 0
            outage_started_at = None
            sleep_fn(interval_seconds)
            continue
        consecutive_failures += 1
        if outage_started_at is None:
            outage_started_at = monotonic_fn()
        outage_seconds = max(0.0, monotonic_fn() - outage_started_at)
        if consecutive_failures < failure_threshold or outage_seconds < min_outage_seconds:
            sleep_fn(interval_seconds)
            continue
        listener_failure_event.set()
        metadata_updater(
            status="failed",
            host=host,
            port=port,
            pid=os.getpid(),
            mode=os.environ.get("MISSION_CONTROL_SERVER_MODE", "daemon"),
            last_error=failure_message,
        )
        sys.stderr.write(failure_message + "\n")
        sys.stderr.flush()
        server.should_exit = True
        sleep_fn(0.25)
        exit_process(1)
        return


def main() -> None:
    ensure_runtime_dirs()
    ensure_daemon_token()
    os.environ.setdefault("MISSION_CONTROL_SERVER_MODE", "daemon")
    if windows_accept_patch_enabled():
        configure_asyncio_runtime()
    from main import app

    binding = resolve_backend_binding(prefer_live_metadata=False)
    host = str(binding["host"])
    port = int(binding["port"])
    if host.strip().lower() not in LOCAL_HOSTS:
        raise RuntimeError(f"Mission Control daemon must stay localhost-only. Refusing host {host!r}.")
    started_at = write_daemon_metadata(
        host=host,
        port=port,
        pid=os.getpid(),
        mode=os.environ["MISSION_CONTROL_SERVER_MODE"],
        status="starting",
    )["started_at"]
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False, loop="asyncio")
    server = uvicorn.Server(config)
    stop_event = threading.Event()
    listener_failure_event = threading.Event()
    guard = threading.Thread(
        target=_listener_guard,
        kwargs={
            "server": server,
            "host": host,
            "port": port,
            "stop_event": stop_event,
            "listener_failure_event": listener_failure_event,
        },
        name="mission-control-listener-guard",
        daemon=True,
    )
    guard.start()
    try:
        sys.stderr.write(f"[mission-control-daemon] starting uvicorn on {host}:{port}\n")
        sys.stderr.flush()
        server.run()
        sys.stderr.write(
            f"[mission-control-daemon] server.run() returned; started={getattr(server, 'started', False)} should_exit={getattr(server, 'should_exit', False)} listener_failure={listener_failure_event.is_set()}\n"
        )
        sys.stderr.flush()
        if listener_failure_event.is_set():
            raise RuntimeError(f"Mission Control daemon listener guard lost localhost health at {host}:{port}.")
        update_daemon_metadata_status(
            status="stopped",
            host=host,
            port=port,
            pid=os.getpid(),
            mode=os.environ["MISSION_CONTROL_SERVER_MODE"],
        )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        write_daemon_metadata(
            host=host,
            port=port,
            pid=os.getpid(),
            mode=os.environ["MISSION_CONTROL_SERVER_MODE"],
            status="failed",
            started_at=started_at,
            last_error=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        stop_event.set()
        guard.join(timeout=1.0)


if __name__ == "__main__":
    main()
