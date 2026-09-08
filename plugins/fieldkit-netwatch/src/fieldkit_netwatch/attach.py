from __future__ import annotations

import ipaddress
import shutil
import subprocess
from dataclasses import dataclass

from fieldkit_netwatch.destinations import identify_service, ip_scope
from fieldkit_netwatch.store import Store


@dataclass(frozen=True)
class SocketObservation:
    """One established TCP socket reported by `lsof`."""

    pid: int
    process_name: str
    local: str
    remote_host: str
    remote_port: int

    @property
    def fingerprint(self) -> str:
        """Stable identity for deduplicating follow-mode snapshots."""

        return f"{self.pid}|{self.local}|{self.remote_host}:{self.remote_port}"


def descendant_pids(root_pid: int, process_table: str | None = None) -> set[int]:
    """Return a PID and every descendant visible in the current process table."""

    if root_pid <= 0:
        raise ValueError("pid must be positive")
    if process_table is None:
        try:
            process_table = subprocess.run(
                ["ps", "-axo", "pid=,ppid="],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(f"can't inspect process tree: {exc}") from exc
    children: dict[int, set[int]] = {}
    visible: set[int] = set()
    for line in process_table.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            pid, ppid = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        visible.add(pid)
        children.setdefault(ppid, set()).add(pid)
    if root_pid not in visible:
        raise ValueError(f"no running process {root_pid}")
    result = {root_pid}
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        for child in children.get(parent, set()):
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def snapshot_process(root_pid: int) -> list[SocketObservation]:
    """Sample established TCP sockets for a process tree through `lsof`."""

    executable = shutil.which("lsof")
    if not executable:
        raise RuntimeError("attach needs lsof, which is not available on this machine")
    pids = descendant_pids(root_pid)
    completed = subprocess.run(
        [
            executable,
            "-nP",
            "-a",
            "-p",
            ",".join(str(pid) for pid in sorted(pids)),
            "-iTCP",
            "-sTCP:ESTABLISHED",
            "-FpcfnT",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(f"lsof failed with status {completed.returncode}")
    return parse_lsof(completed.stdout)


def parse_lsof(output: str) -> list[SocketObservation]:
    """Parse machine-readable `lsof -FpcfnT` output."""

    observations: list[SocketObservation] = []
    pid: int | None = None
    process_name = "unknown"
    for line in output.splitlines():
        if not line:
            continue
        code, value = line[0], line[1:]
        if code == "p":
            try:
                pid = int(value)
            except ValueError:
                pid = None
        elif code == "c":
            process_name = value or "unknown"
        elif code == "n" and pid is not None and "->" in value:
            local, remote = value.split("->", 1)
            remote = remote.split(" ", 1)[0]
            try:
                host, port = _split_endpoint(remote)
            except ValueError:
                continue
            observations.append(SocketObservation(pid, process_name, local, host, port))
    return observations


def record_snapshot(store: Store, session_id: str, root_pid: int) -> int:
    """Sample and persist only sockets not already seen in this attach session."""

    added = 0
    for observation in snapshot_process(root_pid):
        if store.record_observation(
            session_id=session_id,
            fingerprint=observation.fingerprint,
            host=observation.remote_host,
            port=observation.remote_port,
            scope=ip_scope(observation.remote_host),
            service=identify_service(observation.remote_host),
            process_pid=observation.pid,
            process_name=observation.process_name,
            detail="sampled established socket; attach cannot enforce or count requests",
        ):
            added += 1
    return added


def _split_endpoint(value: str) -> tuple[str, int]:
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or not value[end + 1 :].startswith(":"):
            raise ValueError("invalid IPv6 endpoint")
        host = value[1:end]
        raw_port = value[end + 2 :]
    else:
        host, separator, raw_port = value.rpartition(":")
        if not separator:
            raise ValueError("invalid endpoint")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ValueError("invalid endpoint port")
    try:
        normalized = str(ipaddress.ip_address(host))
    except ValueError:
        normalized = host.lower().rstrip(".")
    return normalized, port
