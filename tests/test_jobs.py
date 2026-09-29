"""Heavy-job admission: a full queue says busy, and arrival order wins over read order."""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request

from fieldkit.web.routes.jobs import (
    HEAVY_REQUEST_BYTES,
    JobCrashed,
    _MAX_ADMITTED,
    _claim_job_id,
    _note_waiting,
    _pump,
    _release_job_id,
    _unwrap,
    arm_heavy_jobs,
    begin_heavy_request,
    end_heavy_request,
    job_is_waiting,
    release_admission,
    stop_heavy_jobs,
)


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def test_heavy_queue_stops_admitting_when_it_is_full() -> None:
    arm_heavy_jobs()
    try:
        held = [_request() for _ in range(_MAX_ADMITTED)]
        assert all(begin_heavy_request(request) for request in held)
        assert begin_heavy_request(_request()) is False
        assert HEAVY_REQUEST_BYTES == 1_000_000
    finally:
        stop_heavy_jobs()


def test_a_ready_job_is_not_blocked_by_an_upload_still_in_flight() -> None:
    arm_heavy_jobs()
    try:
        first, second = _request(), _request()
        assert begin_heavy_request(first)
        assert begin_heavy_request(second)
        second.state.heavy_ticket.ready = True
        _pump()
        assert first.state.heavy_ticket.granted.is_set() is False
        assert second.state.heavy_ticket.granted.is_set() is True
    finally:
        stop_heavy_jobs()


def test_ready_jobs_keep_arrival_order() -> None:
    arm_heavy_jobs()
    try:
        held, first, second = _request(), _request(), _request()
        assert begin_heavy_request(held)
        assert begin_heavy_request(first)
        assert begin_heavy_request(second)
        held.state.heavy_ticket.ready = True
        held.state.heavy_ticket.running = True
        held.state.heavy_ticket.granted.set()
        first.state.heavy_ticket.ready = True
        second.state.heavy_ticket.ready = True
        _pump()
        assert first.state.heavy_ticket.granted.is_set() is True
        assert second.state.heavy_ticket.granted.is_set() is False
    finally:
        stop_heavy_jobs()


def test_worker_input_errors_stay_validation_and_crashes_hide_the_message() -> None:
    with pytest.raises(ValueError, match="invalid XLSX archive"):
        _unwrap("err", ValueError("invalid XLSX archive"))
    with pytest.raises(JobCrashed, match="^MemoryError$") as raised:
        _unwrap("err", MemoryError("arena details"))
    assert "arena" not in str(raised.value)


def test_client_disconnect_releases_the_admission_place() -> None:
    arm_heavy_jobs()
    try:
        held = []
        for _ in range(_MAX_ADMITTED):
            request = _request()
            assert begin_heavy_request(request)
            held.append(request)
        assert begin_heavy_request(_request()) is False

        release_admission(held[0])
        replacement = _request()
        assert begin_heavy_request(replacement) is True
        # The disconnected request's cleanup must not free a second place.
        asyncio.run(end_heavy_request(held[0]))
        assert begin_heavy_request(_request()) is False
    finally:
        stop_heavy_jobs()


def test_queue_flag_follows_the_job_id() -> None:
    arm_heavy_jobs()
    try:
        assert job_is_waiting("abcdefgh") is False
        assert _claim_job_id("abcdefgh") == "abcdefgh"
        _note_waiting("abcdefgh", True)
        assert job_is_waiting("abcdefgh") is True
        assert _claim_job_id("abcdefgh") == ""
        _release_job_id("abcdefgh")
        assert job_is_waiting("abcdefgh") is False
    finally:
        stop_heavy_jobs()
