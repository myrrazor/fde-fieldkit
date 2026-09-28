"""Heavy-job admission: a full queue says busy, and arrival order wins over read order."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from fieldkit.web.routes.jobs import (
    HEAVY_REQUEST_BYTES,
    JobCrashed,
    _MAX_ADMITTED,
    _note_waiting,
    _pump,
    _unwrap,
    arm_heavy_jobs,
    begin_heavy_request,
    job_is_waiting,
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


def test_a_later_upload_cannot_start_ahead_of_an_earlier_one() -> None:
    arm_heavy_jobs()
    try:
        first, second = _request(), _request()
        assert begin_heavy_request(first)
        assert begin_heavy_request(second)
        second.state.heavy_ticket.ready = True
        _pump()
        assert second.state.heavy_ticket.granted.is_set() is False

        first.state.heavy_ticket.ready = True
        _pump()
        assert first.state.heavy_ticket.granted.is_set() is True
        assert first.state.heavy_ticket.running is True
        assert second.state.heavy_ticket.granted.is_set() is True
    finally:
        stop_heavy_jobs()


def test_dropping_an_earlier_upload_lets_the_next_job_through() -> None:
    arm_heavy_jobs()
    try:
        first, second = _request(), _request()
        assert begin_heavy_request(first)
        assert begin_heavy_request(second)
        second.state.heavy_ticket.ready = True
        _pump()
        assert second.state.heavy_ticket.granted.is_set() is False
        first.state.heavy_ticket.done = True
        _pump()
        assert second.state.heavy_ticket.granted.is_set() is True
    finally:
        stop_heavy_jobs()


def test_worker_input_errors_stay_validation_and_crashes_hide_the_message() -> None:
    with pytest.raises(ValueError, match="invalid XLSX archive"):
        _unwrap("err", ValueError("invalid XLSX archive"))
    with pytest.raises(JobCrashed, match="^MemoryError$") as raised:
        _unwrap("err", MemoryError("arena details"))
    assert "arena" not in str(raised.value)


def test_queue_flag_follows_the_job_id() -> None:
    arm_heavy_jobs()
    try:
        assert job_is_waiting("abcdefgh") is False
        _note_waiting("abcdefgh", True)
        assert job_is_waiting("abcdefgh") is True
        _note_waiting("abcdefgh", False)
        assert job_is_waiting("abcdefgh") is False
    finally:
        stop_heavy_jobs()
