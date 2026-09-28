"""Run heavy hub work off the event loop, one at a time, and stop it if the client leaves."""

from __future__ import annotations

import asyncio
import ctypes
import gc
import multiprocessing as mp
from collections.abc import Callable
from queue import Empty
from typing import Any

from starlette.requests import Request

# Past this size the work runs in a child process. The parent keeps the GIL,
# so a profile or a scrub does not stall the rest of the hub, and the child
# can be killed when the browser disconnects or the server shuts down.
_ISOLATE_BYTES = 1_000_000
_LIVE: set[mp.Process] = set()
_semaphore: asyncio.Semaphore | None = None
_shutting_down = False


class ClientGone(Exception):
    """The browser went away before a heavy job finished."""


def arm_heavy_jobs() -> None:
    """Allow isolated jobs. A previous server in this process may have stopped them."""

    global _shutting_down
    _shutting_down = False


def stop_heavy_jobs() -> None:
    """Kill any isolated job still running. Called on server shutdown."""

    global _shutting_down
    _shutting_down = True
    for proc in list(_LIVE):
        _kill(proc)


async def run_job(
    request: Request,
    fn: Callable[..., Any],
    /,
    *args: Any,
    weight: int = 0,
    isolate: bool = False,
) -> Any:
    """Run ``fn(*args)`` without blocking the event loop.

    Large inputs run in one child process. Further large inputs wait, and a
    disconnected client is dropped instead of starting or finishing the work.
    """

    if isolate or weight >= _ISOLATE_BYTES:
        return await _run_isolated(request, fn, args)
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, *args)


async def _run_isolated(request: Request, fn: Callable[..., Any], args: tuple[Any, ...]) -> Any:
    sem = _heavy_semaphore()
    # Starlette's is_disconnected() cancels the read immediately, so a browser
    # abort that arrives while the child is working is easy to miss. Park on
    # the ASGI receive channel instead; the body has already been read.
    gone = asyncio.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, gone))
    acquired = False
    try:
        while not acquired:
            if _shutting_down or gone.is_set():
                raise ClientGone()
            try:
                await asyncio.wait_for(sem.acquire(), timeout=0.2)
                acquired = True
            except TimeoutError:
                continue
        if _shutting_down or gone.is_set():
            raise ClientGone()
        return await _spawn(fn, args, gone)
    finally:
        watcher.cancel()
        try:
            await watcher
        except (asyncio.CancelledError, Exception):
            pass
        if acquired:
            sem.release()
        _release_memory()


async def _watch_disconnect(request: Request, gone: asyncio.Event) -> None:
    try:
        while True:
            message = await request._receive()  # noqa: SLF001
            if isinstance(message, dict) and message.get("type") == "http.disconnect":
                gone.set()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        gone.set()


async def _spawn(fn: Callable[..., Any], args: tuple[Any, ...], gone: asyncio.Event) -> Any:
    ctx = mp.get_context("spawn")
    queue: mp.Queue[tuple[str, Any]] = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(fn, args, queue), daemon=False)
    # Pickling a multi-megabyte upload is synchronous. Do it off the loop so
    # health and the other tools stay responsive while a heavy job starts.
    await asyncio.to_thread(proc.start)
    _LIVE.add(proc)
    completed = False
    try:
        while True:
            if _shutting_down or gone.is_set():
                raise ClientGone()
            try:
                kind, payload = await asyncio.to_thread(queue.get, True, 0.05)
            except Empty:
                if not proc.is_alive():
                    if _shutting_down:
                        raise ClientGone()
                    raise RuntimeError("heavy job stopped before returning a result")
                continue
            completed = True
            return _unwrap(kind, payload)
    finally:
        # A finished child should exit on its own. Terminate only when the
        # client left or the server is stopping, so the queue semaphore is
        # not abandoned on the success path.
        if completed:
            proc.join(timeout=0.5)
        if not completed or proc.is_alive():
            _kill(proc)
        _LIVE.discard(proc)
        queue.close()
        queue.cancel_join_thread()


def _unwrap(kind: str, payload: Any) -> Any:
    if kind == "ok":
        return payload
    if isinstance(payload, BaseException):
        raise payload
    raise RuntimeError(str(payload))


def _worker(fn: Callable[..., Any], args: tuple[Any, ...], queue: mp.Queue[tuple[str, Any]]) -> None:
    try:
        queue.put(("ok", fn(*args)))
    except Exception as exc:
        queue.put(("err", exc))


def _heavy_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(1)
    return _semaphore


def _kill(proc: mp.Process) -> None:
    if not proc.is_alive():
        proc.join(timeout=0.2)
        return
    proc.terminate()
    proc.join(timeout=0.5)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=0.5)


def _release_memory() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        return
