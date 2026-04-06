import json
import threading
from typing import Dict, Mapping, MutableMapping, Optional


class VectorClock:
    def __init__(self, node_id: str, initial: Optional[Mapping[str, int]] = None):
        self.node_id = node_id
        self._lock = threading.Lock()
        self._clock: Dict[str, int] = self._normalize(initial)
        self._clock.setdefault(self.node_id, 0)

    @staticmethod
    def _normalize(clock: Optional[Mapping[str, int]]) -> Dict[str, int]:
        normalized: Dict[str, int] = {}
        if not clock:
            return normalized
        for key, value in clock.items():
            normalized[str(key)] = int(value)
        return normalized

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._clock)

    def send_event(self) -> Dict[str, int]:
        with self._lock:
            self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1
            return dict(self._clock)

    def receive_event(self, incoming: Optional[Mapping[str, int]]) -> Dict[str, int]:
        with self._lock:
            merged = self._normalize(incoming)
            for node_id, value in merged.items():
                self._clock[node_id] = max(self._clock.get(node_id, 0), value)
            self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1
            return dict(self._clock)

    def local_event(self) -> Dict[str, int]:
        with self._lock:
            self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1
            return dict(self._clock)

    @staticmethod
    def merge_clocks(*clocks: Optional[Mapping[str, int]]) -> Dict[str, int]:
        merged: Dict[str, int] = {}
        for clock in clocks:
            if not clock:
                continue
            for key, value in clock.items():
                node_id = str(key)
                merged[node_id] = max(merged.get(node_id, 0), int(value))
        return merged

    @staticmethod
    def happened_before(vc1: Mapping[str, int], vc2: Mapping[str, int]) -> bool:
        keys = set(vc1) | set(vc2)
        less_than = False
        for key in keys:
            left = int(vc1.get(key, 0))
            right = int(vc2.get(key, 0))
            if left > right:
                return False
            if left < right:
                less_than = True
        return less_than

    @staticmethod
    def concurrent(vc1: Mapping[str, int], vc2: Mapping[str, int]) -> bool:
        return not VectorClock.happened_before(vc1, vc2) and not VectorClock.happened_before(vc2, vc1)


def vector_clock_to_metadata(clock: Mapping[str, int]) -> str:
    return json.dumps({str(key): int(value) for key, value in clock.items()}, sort_keys=True)


def vector_clock_from_metadata(metadata: Optional[MutableMapping[str, str]] = None) -> Dict[str, int]:
    if not metadata:
        return {}
    raw_clock = metadata.get("x-vector-clock")
    if not raw_clock:
        return {}
    return {str(key): int(value) for key, value in json.loads(raw_clock).items()}
