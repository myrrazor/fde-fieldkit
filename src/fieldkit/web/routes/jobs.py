"""Run heavy hub work off the event loop and stop it when the client or the parent goes away."""

from __future__ import annotations

import asyncio
import ctypes
import gc
import multiprocessing as mp
import os
import re
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Empty
from typing import Any

from starlette.requests import Request

# Past this size the work runs in a child process. Two children is enough for
# a small profile to start while a large scrub is still going. Further work
# waits in arrival order. Only a few large bodies may sit in that queue.
HEAVY_REQUEST_BYTES = 1_000_000
_HEAVY_SLOTS = 2
_MAX_WAITING = 4
_MAX_ADMITTED = _HEAVY_SLOTS + _MAX_WAITING
_JOB_ID = re.compile(r"^[A-Za-z0-9]{8,64}$")

_LIVE: set[mp.Process] = set()
_POOL: list[_Worker] = []
_idle: asyncio.Queue[_Worker] | None = None
_tickets: list[_Ticket] = []
_waiting: set[str] = set()
_claimed: set[str] = set()
_admitted = 0
_seq = 0
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


@dataclass
class _Ticket:
    """One heavy request, in the order its headers arrived."""

    seq: int
    ready: bool = False
    running: bool = False
    done: bool = False
    granted: asyncio.Event = field(default_factory=asyncio.Event)


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


def begin_heavy_request(request: Request) -> bool:
    """Reserve a place for a large upload. False when the waiting queue is full."""

    global _admitted, _seq
    if _shutting_down or _admitted >= _MAX_ADMITTED:
        return False
    _admitted += 1
    _seq += 1
    ticket = _Ticket(_seq)
    _tickets.append(ticket)
    request.state.heavy_admitted = True
    request.state.heavy_ticket = ticket
    return True


def release_admission(request: Request) -> None:
    """Free the cap as soon as the client leaves, without waiting for the handler."""

    global _admitted
    if not getattr(request.state, "heavy_admitted", False):
        return
    if getattr(request.state, "admission_released", False):
        return
    request.state.admission_released = True
    if _admitted:
        _admitted -= 1


async def end_heavy_request(request: Request) -> None:
    """Drop a large upload's buffers once the request is over."""

    if not getattr(request.state, "heavy_admitted", False):
        return
    release_admission(request)
    request.state.heavy_admitted = False
    ticket = getattr(request.state, "heavy_ticket", None)
    if ticket is not None and not ticket.done:
        _finish_ticket(ticket)
    await _drop_request_buffers(request)
    _release_memory()


def job_is_waiting(job_id: str) -> bool:
    """True when this browser request is queued behind another heavy job."""

    return bool(job_id) and job_id in _waiting


def _reset_pool() -> None:
    global _idle, _admitted, _seq
    for worker in list(_POOL):
        _dispose(worker)
    for proc in list(_LIVE):
        _kill(proc)
    _POOL.clear()
    _LIVE.clear()
    for ticket in _tickets:
        ticket.done = True
        ticket.granted.set()
    _tickets.clear()
    _waiting.clear()
    _claimed.clear()
    _admitted = 0
    _seq = 0
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

    if isolate or weight >= HEAVY_REQUEST_BYTES:
        return await _run_isolated(request, fn, args)
    # A chunked body we counted early turned out small. Give the place back.
    if getattr(request.state, "heavy_provisional", False):
        release_admission(request)
        request.state.heavy_provisional = False
    _skip_heavy_ticket(request)
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, *args)


async def _run_isolated(request: Request, fn: Callable[..., Any], args: tuple[Any, ...]) -> Any:
    # Starlette's is_disconnected() cancels the read immediately, so a browser
    # abort that arrives while the child is working is easy to miss. Park on
    # the ASGI receive channel instead; the body has already been read.
    gone = asyncio.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, gone))
    ticket = _claim_ticket(request)
    job_id = _claim_job_id(_job_id(request))
    worker: _Worker | None = None
    reuse = False
    try:
        await _await_slot(ticket, gone, job_id)
        if _shutting_down or gone.is_set():
            raise _gone_now()
        worker = await _take_worker()
        if _shutting_down or gone.is_set():
            raise _gone_now()
        result = await _invoke(worker, fn, args, gone)
        # A multi-megabyte frame stays in the child heap. Recycle that process
        # so the memory comes back. Smaller isolated jobs keep the process,
        # because starting a new one would dominate their runtime.
        reuse = not _heavy_payload(args)
        return result
    finally:
        _release_job_id(job_id)
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
        _finish_ticket(ticket)
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


def _job_id(request: Request) -> str:
    raw = request.headers.get("x-fieldkit-job", "")
    return raw if _JOB_ID.fullmatch(raw) else ""


def _note_waiting(job_id: str, waiting: bool) -> None:
    if not job_id or job_id not in _claimed:
        return
    if waiting:
        _waiting.add(job_id)
    else:
        _waiting.discard(job_id)


def _claim_job_id(raw: str) -> str:
    """One id belongs to one request. A reused id does not attach to this one."""

    if not raw or raw in _claimed:
        return ""
    _claimed.add(raw)
    return raw


def _release_job_id(job_id: str) -> None:
    if not job_id:
        return
    _claimed.discard(job_id)
    _waiting.discard(job_id)


def _claim_ticket(request: Request) -> _Ticket:
    """Take this request's arrival ticket, or open a new one at the back."""

    global _seq
    ticket = getattr(request.state, "heavy_ticket", None)
    if ticket is None or ticket.done:
        _seq += 1
        ticket = _Ticket(_seq, ready=True)
        _tickets.append(ticket)
        request.state.heavy_ticket = ticket
    else:
        ticket.ready = True
    _pump()
    return ticket


def _skip_heavy_ticket(request: Request) -> None:
    """This request will not take a worker. Let later jobs pass it."""

    ticket = getattr(request.state, "heavy_ticket", None)
    if ticket is None or ticket.done or ticket.running:
        return
    ticket.done = True
    request.state.heavy_ticket = None
    _pump()


def _finish_ticket(ticket: _Ticket) -> None:
    if ticket.done:
        return
    ticket.done = True
    ticket.running = False
    _pump()


def _pump() -> None:
    """Hand free slots to ready requests, earliest first.

    A body that has not finished arriving does not hold the line. Ready
    work starts while that upload is still on the socket.
    """

    while _tickets and _tickets[0].done:
        _tickets.pop(0)
    running = sum(1 for ticket in _tickets if ticket.running)
    for ticket in _tickets:
        if ticket.done or ticket.running:
            continue
        if not ticket.ready:
            continue
        if running >= _HEAVY_SLOTS:
            break
        ticket.running = True
        running += 1
        ticket.granted.set()


async def _await_slot(ticket: _Ticket, gone: asyncio.Event, job_id: str) -> None:
    if not ticket.granted.is_set():
        _note_waiting(job_id, True)
        waiter = asyncio.create_task(ticket.granted.wait())
        stopper = asyncio.create_task(_until_stopped(gone))
        try:
            done, _pending = await asyncio.wait(
                {waiter, stopper}, return_when=asyncio.FIRST_COMPLETED
            )
        except asyncio.CancelledError:
            stopper.cancel()
            waiter.cancel()
            _note_waiting(job_id, False)
            _finish_ticket(ticket)
            raise
        _note_waiting(job_id, False)
        if waiter not in done or _shutting_down or gone.is_set():
            stopper.cancel()
            if not waiter.done():
                waiter.cancel()
            await _quiet(stopper)
            await _quiet(waiter)
            _finish_ticket(ticket)
            raise _gone_now()
        stopper.cancel()
        await _quiet(stopper)
    if _shutting_down or gone.is_set():
        _finish_ticket(ticket)
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
        # The class name is enough. The message can be a parser's internal text.
        raise JobCrashed(type(payload).__name__)
    raise JobCrashed("stopped before returning a result")


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


async def _drop_request_buffers(request: Request) -> None:
    """Close spooled uploads and drop the parsed form so the bytes can leave RSS."""

    form = getattr(request, "_form", None)
    if form is not None:
        try:
            await form.close()
        except Exception:
            pass
        request._form = None  # noqa: SLF001
    if hasattr(request, "_body"):
        request._body = b""  # noqa: SLF001


def _release_memory() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        return
