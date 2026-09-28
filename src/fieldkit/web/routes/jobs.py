"""Run heavy hub work off the event loop and stop it when the client or the parent goes away."""

from __future__ import annotations

import asyncio
import ctypes
import gc
import multiprocessing as mp
import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty
from typing import Any

from starlette.requests import Request

# Past this size the work runs in a child process. Two children is enough for
# a small profile to start while a large scrub is still going, without a pile
# of 49 MB jobs resident at once. Further work waits in submit order.
_ISOLATE_BYTES = 1_000_000
_HEAVY_SLOTS = 2
_LIVE: set[mp.Process] = set()
_POOL: list[_Worker] = []
_semaphore: asyncio.Semaphore | None = None
_idle: asyncio.Queue[_Worker] | None = None
_shutting_down = False


class ClientGone(Exception):
    """The browser went away, or the server stopped, before a heavy job finished."""

    def __init__(self, reason: str = "disconnect") -> None:
        super().__init__(reason)
        self.reason = reason


class JobCrashed(Exception):
    """The child died before it could return a result."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Worker:
    proc: mp.Process
    inbox: mp.Queue[Any]
    outbox: mp.Queue[Any]
    closed: bool = False


def arm_heavy_jobs() -> None:
    """Allow isolated jobs. A previous server in this process may have stopped them."""

    global _shutting_down
    _shutting_down = False
    _reset_pool()


def stop_heavy_jobs() -> None:
    """Kill any isolated job still running. Called on server shutdown."""

    global _shutting_down
    _shutting_down = True
    _reset_pool()


def _reset_pool() -> None:
    global _semaphore, _idle
    for worker in list(_POOL):
        _dispose(worker)
    for proc in list(_LIVE):
        _kill(proc)
    _POOL.clear()
    _LIVE.clear()
    _semaphore = None
    _idle = None


async def run_job(
    request: Request,
    fn: Callable[..., Any],
    /,
    *args: Any,
    weight: int = 0,
    isolate: bool = False,
) -> Any:
    """Run ``fn(*args)`` without blocking the event loop.

    Large inputs run in a child process, two at a time, in the order they
    arrived. A disconnected client is dropped instead of starting or finishing
    the work. The child exits if this process dies hard.
    """

    if isolate or weight >= _ISOLATE_BYTES:
        return await _run_isolated(request, fn, args)
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, *args)


async def _run_isolated(request: Request, fn: Callable[..., Any], args: tuple[Any, ...]) -> Any:
    # Starlette's is_disconnected() cancels the read immediately, so a browser
    # abort that arrives while the child is working is easy to miss. Park on
    # the ASGI receive channel instead; the body has already been read.
    gone = asyncio.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, gone))
    sem: asyncio.Semaphore | None = None
    worker: _Worker | None = None
    reuse = False
    try:
        sem, worker = await _acquire_worker(gone)
        if _shutting_down or gone.is_set():
            raise _gone_now()
        result = await _invoke(worker, fn, args, gone)
        # A multi-megabyte frame stays in the child heap. Recycle that process
        # so the memory comes back. Smaller isolated jobs keep the process,
        # because starting a new one would dominate their runtime.
        reuse = not _heavy_payload(args)
        return result
    finally:
        watcher.cancel()
        try:
            await watcher
        except (asyncio.CancelledError, Exception):
            pass
        if worker is not None:
            # Return the warm process before releasing the slot so the next
            # waiter reuses it instead of starting a third child.
            if reuse and worker.proc.is_alive() and not _shutting_down:
                _idle_workers().put_nowait(worker)
            else:
                _dispose(worker)
        if sem is not None:
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


def _gone_now() -> ClientGone:
    return ClientGone("shutdown" if _shutting_down else "disconnect")


def _heavy_payload(args: tuple[Any, ...]) -> bool:
    total = 0
    for arg in args:
        if isinstance(arg, (bytes, bytearray, str)):
            total += len(arg)
    return total >= 8_000_000


async def _acquire_worker(gone: asyncio.Event) -> tuple[asyncio.Semaphore, _Worker]:
    sem = _heavy_semaphore()
    await _acquire_permit(sem, gone)
    try:
        worker = await _take_worker()
    except BaseException:
        sem.release()
        raise
    return sem, worker


async def _acquire_permit(sem: asyncio.Semaphore, gone: asyncio.Event) -> None:
    # Waiting on acquire() itself keeps submit order. A timeout that cancels
    # the wait puts the oldest job at the back of the line.
    waiting = asyncio.create_task(sem.acquire())
    stopper = asyncio.create_task(_until_stopped(gone))
    try:
        done, _pending = await asyncio.wait(
            {waiting, stopper}, return_when=asyncio.FIRST_COMPLETED
        )
    except asyncio.CancelledError:
        stopper.cancel()
        if waiting.done() and not waiting.cancelled():
            sem.release()
        else:
            waiting.cancel()
        raise
    if waiting in done:
        stopper.cancel()
        await _quiet(stopper)
        if _shutting_down or gone.is_set():
            sem.release()
            raise _gone_now()
        return
    waiting.cancel()
    try:
        await waiting
    except asyncio.CancelledError:
        pass
    else:
        sem.release()
    raise _gone_now()


async def _until_stopped(gone: asyncio.Event) -> None:
    while not _shutting_down and not gone.is_set():
        await asyncio.sleep(0.05)


async def _quiet(task: asyncio.Task[Any]) -> None:
    try:
        await task
    except (asyncio.CancelledError, Exception):
        return


async def _take_worker() -> _Worker:
    idle = _idle_workers()
    while True:
        try:
            worker = idle.get_nowait()
        except asyncio.QueueEmpty:
            return await _start_worker()
        if worker.proc.is_alive():
            return worker
        _dispose(worker)


async def _start_worker() -> _Worker:
    ctx = mp.get_context("spawn")
    inbox: mp.Queue[Any] = ctx.Queue()
    outbox: mp.Queue[Any] = ctx.Queue()
    proc = ctx.Process(target=_warm_worker, args=(inbox, outbox), daemon=False)
    await asyncio.to_thread(proc.start)
    worker = _Worker(proc, inbox, outbox)
    _LIVE.add(proc)
    _POOL.append(worker)
    return worker


async def _invoke(
    worker: _Worker,
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    gone: asyncio.Event,
) -> Any:
    # Pickling a multi-megabyte upload is synchronous. Do it off the loop so
    # health and the other tools stay responsive while a heavy job starts.
    await asyncio.to_thread(worker.inbox.put, (fn, args))
    while True:
        if _shutting_down or gone.is_set():
            raise _gone_now()
        try:
            kind, payload = await asyncio.to_thread(worker.outbox.get, True, 0.05)
        except Empty:
            if not worker.proc.is_alive():
                if _shutting_down or gone.is_set():
                    raise _gone_now()
                raise JobCrashed("stopped before returning a result")
            continue
        return _unwrap(kind, payload)


def _unwrap(kind: str, payload: Any) -> Any:
    if kind == "ok":
        return payload
    if isinstance(payload, ValueError):
        raise payload
    if isinstance(payload, BaseException):
        reason = str(payload).strip() or payload.__class__.__name__
        raise JobCrashed(reason)
    raise JobCrashed(str(payload))


def _warm_worker(inbox: mp.Queue[Any], outbox: mp.Queue[Any]) -> None:
    _die_with_parent()
    while True:
        item = inbox.get()
        if item is None:
            return
        fn, args = item
        try:
            outbox.put(("ok", fn(*args)))
        except Exception as exc:
            try:
                outbox.put(("err", exc))
            except Exception:
                os._exit(1)
        _release_memory()


def _die_with_parent() -> None:
    """Exit when the hub process dies, including kill -9 (no signal handler runs there)."""

    if os.name != "posix":
        return
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        # 1 is PR_SET_PDEATHSIG. SIGKILL cannot be caught by the child.
        libc.prctl(1, signal.SIGKILL)
    except (OSError, AttributeError):
        pass
    if os.getppid() == 1:
        os._exit(1)
    parent = os.getppid()

    def _watch() -> None:
        while True:
            time.sleep(0.3)
            if os.getppid() != parent:
                os._exit(1)

    threading.Thread(target=_watch, name="fieldkit-parent", daemon=True).start()


def _heavy_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_HEAVY_SLOTS)
    return _semaphore


def _idle_workers() -> asyncio.Queue[_Worker]:
    global _idle
    if _idle is None:
        _idle = asyncio.Queue()
    return _idle


def _dispose(worker: _Worker) -> None:
    if worker.closed:
        return
    worker.closed = True
    _kill(worker.proc)
    _LIVE.discard(worker.proc)
    if worker in _POOL:
        _POOL.remove(worker)
    for queue in (worker.inbox, worker.outbox):
        queue.close()
        queue.cancel_join_thread()


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
