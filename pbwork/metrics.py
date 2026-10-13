"""Exact counters with bounded deterministic latency samples."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

COUNTERS = ("attempted", "completed", "failed", "retried", "committed", "rolled_back", "rows_read", "rows_written", "requested_rows", "empty_results", "contention_events", "timeouts", "deadlocks")


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 6)


@dataclass
class RunMetrics:
    sample_limit: int = 100000
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNTERS, 0))
    _samples: list[tuple[int, float]] = field(default_factory=list)
    _by_operation: dict[str, "RunMetrics"] = field(default_factory=dict)
    _traversal_depth: int = 0
    _lob_modes: set[str] = field(default_factory=set)

    def record(self, operation_id: str, ordinal: int, response: dict, *, nested: bool = False):
        status = response.get("status", "failed")
        self.counts["attempted"] += 1
        self.counts["completed" if status in {"read", "committed"} else "failed"] += 1
        self.counts["committed"] += int(status == "committed")
        self.counts["rolled_back"] += int(status == "rolled_back")
        for key in ("rows_read", "rows_written"):
            self.counts[key] += int(response.get(key, 0))
        self.counts["requested_rows"] += int(response.get("requested_cardinality", 0))
        self.counts["empty_results"] += int(status == "read" and int(response.get("rows_read", 0)) == 0)
        self._traversal_depth = max(self._traversal_depth, int(response.get("traversal_depth") or 0))
        if response.get("lob_mode"):
            self._lob_modes.add(str(response["lob_mode"]))
        for key in ("retried", "contention_events", "timeouts", "deadlocks"):
            self.counts[key] += int(response.get(key, 0))
        latency = max(0.0, float(response.get("elapsed_ms", 0)))
        rank = int.from_bytes(hashlib.sha256(f"{operation_id}:{ordinal}".encode()).digest()[:8], "big")
        if len(self._samples) < self.sample_limit:
            self._samples.append((rank, latency))
        elif self.sample_limit and rank < max(self._samples)[0]:
            self._samples[self._samples.index(max(self._samples))] = (rank, latency)
        if not nested:
            child = self._by_operation.setdefault(operation_id, RunMetrics(self.sample_limit))
            child.record(operation_id, ordinal, response, nested=True)

    def latency(self) -> dict:
        values = [value for _, value in self._samples]
        return {"median": _percentile(values, .5), "p95": _percentile(values, .95),
                "p99": _percentile(values, .99), "sample_count": len(values), "sample_limit": self.sample_limit}

    def as_dict(self, elapsed_seconds: float) -> dict:
        data = dict(self.counts)
        seconds = max(elapsed_seconds, 1e-9)
        data["throughput_ops_per_second"] = round(self.counts["completed"] / seconds, 6)
        data["throughput_rows_per_second"] = round((self.counts["rows_read"] + self.counts["rows_written"]) / seconds, 6)
        data["latency_ms"] = self.latency()
        data["traversal_depth"] = self._traversal_depth
        data["lob_modes"] = sorted(self._lob_modes)
        return data

    def by_operation(self, elapsed_seconds: float) -> dict[str, dict]:
        return {key: value.as_dict(elapsed_seconds) for key, value in self._by_operation.items()}
