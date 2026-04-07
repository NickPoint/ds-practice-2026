import json
import threading
from typing import Dict, Mapping, MutableMapping, Optional


class VectorClock:
    def __init__(self, node_id: str, initial: Optional[Mapping[str, int]] = None):
        # Each process keeps its own logical time plus the latest time observed from others.
        self.node_id = node_id
        self._lock = threading.Lock()
        self._clock: Dict[str, int] = self._normalize(initial)
        self._clock.setdefault(self.node_id, 0)

    @staticmethod
    def _normalize(clock: Optional[Mapping[str, int]]) -> Dict[str, int]:
        # Canonicalize a clock payload so merge/comparison logic always works on {node_id: int}
        normalized: Dict[str, int] = {}
        if not clock:
            return normalized
        for key, value in clock.items():
            normalized[str(key)] = int(value)
        return normalized

    def snapshot(self) -> Dict[str, int]:
        # Return the current vector without advancing logical time
        with self._lock:
            return dict(self._clock)

    def send_event(self) -> Dict[str, int]:
        # Vector clock rule for send: advance the local component before sending the message
        with self._lock:
            self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1
            return dict(self._clock)

    def receive_event(self, incoming: Optional[Mapping[str, int]]) -> Dict[str, int]:
        # Vector clock rule for receive: merge component-wise max, then advance the receiver
        with self._lock:
            merged = self._normalize(incoming)
            for node_id, value in merged.items():
                self._clock[node_id] = max(self._clock.get(node_id, 0), value)
            self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1
            return dict(self._clock)

    def local_event(self) -> Dict[str, int]:
        # Internal events also advance only the local component.
        with self._lock:
            self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1
            return dict(self._clock)

    @staticmethod
    def merge_clocks(*clocks: Optional[Mapping[str, int]]) -> Dict[str, int]:
        # Pure merge helper: component-wise max without creating a new event
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
        # vc1 -> vc2 iff every component in vc1 is <= vc2 and at least one is strictly smaller
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
        # Two events are concurrent when neither vector clock happened before the other.
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
