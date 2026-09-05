"""Explicit finite state machine for the sampling mission (no ROS imports).

Input
-----
A parsed :class:`~.route_model.Route` (map-frame), and time (seconds) provided
either explicitly to :meth:`advance` or via an injected time source.

Output
------
The current :class:`MissionState` and a queue of :class:`StateEvent` objects
emitted on transitions and sampling events.

States
------
``IDLE -> TASK_LOADED -> NAVIGATING -> ARRIVED -> SETTLING ->
SAMPLE_REQUESTED -> SAMPLING -> SAMPLE_FINISHED -> (NAVIGATING | TASK_FINISHED)``
plus terminal ``STOPPED`` and ``FAULT``.

Completion criteria
-------------------
Arriving at a ``sampling`` waypoint triggers a ``sampling_duration_s`` dwell
(default 2 s, the simulated sample) before emitting a ``sample_finished``
event and advancing to the next waypoint (or ``TASK_FINISHED`` on the last
one).  Every transition is validated against an explicit transition table.
"""

from __future__ import annotations

import enum
import time as _time
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from .route_model import Route, Waypoint

TimeSource = Callable[[], float]


class MissionState(enum.Enum):
    IDLE = "IDLE"
    TASK_LOADED = "TASK_LOADED"
    NAVIGATING = "NAVIGATING"
    ARRIVED = "ARRIVED"
    SETTLING = "SETTLING"
    SAMPLE_REQUESTED = "SAMPLE_REQUESTED"
    SAMPLING = "SAMPLING"
    SAMPLE_FINISHED = "SAMPLE_FINISHED"
    PAUSED = "PAUSED"
    RETURNING = "RETURNING"
    TASK_FINISHED = "TASK_FINISHED"
    STOPPED = "STOPPED"
    FAULT = "FAULT"


@dataclass(frozen=True)
class StateEvent:
    """An event emitted by the state machine."""

    kind: str
    state: MissionState
    waypoint_seq: Optional[int] = None
    sample_id: Optional[str] = None
    message: Optional[str] = None


# Explicit transition table: state -> set of allowed successor states.
_TRANSITIONS: Dict[MissionState, FrozenSet[MissionState]] = {
    MissionState.IDLE: frozenset({MissionState.TASK_LOADED}),
    MissionState.TASK_LOADED: frozenset({MissionState.NAVIGATING}),
    MissionState.NAVIGATING: frozenset({MissionState.ARRIVED, MissionState.PAUSED, MissionState.RETURNING}),
    MissionState.RETURNING: frozenset({MissionState.ARRIVED, MissionState.PAUSED}),
    MissionState.ARRIVED: frozenset({MissionState.SETTLING}),
    MissionState.SETTLING: frozenset(
        {MissionState.SAMPLE_REQUESTED, MissionState.NAVIGATING, MissionState.TASK_FINISHED}
    ),
    MissionState.SAMPLE_REQUESTED: frozenset({MissionState.SAMPLING}),
    MissionState.SAMPLING: frozenset({MissionState.SAMPLE_FINISHED}),
    MissionState.SAMPLE_FINISHED: frozenset(
        {MissionState.NAVIGATING, MissionState.TASK_FINISHED}
    ),
    MissionState.PAUSED: frozenset({MissionState.NAVIGATING, MissionState.RETURNING, MissionState.STOPPED}),
    MissionState.TASK_FINISHED: frozenset(),
    MissionState.STOPPED: frozenset(),
    MissionState.FAULT: frozenset(),
}

_TERMINAL = frozenset(
    {MissionState.STOPPED, MissionState.FAULT, MissionState.TASK_FINISHED}
)
_DEAD = frozenset({MissionState.STOPPED, MissionState.FAULT})


class SamplingStateMachine:
    """Explicit FSM driving waypoint arrival, settling and sampling dwell."""

    def __init__(
        self,
        sampling_duration_s: float = 2.0,
        settle_duration_s: float = 0.0,
        time_source: TimeSource = _time.monotonic,
    ) -> None:
        if sampling_duration_s < 0.0:
            raise ValueError("sampling_duration_s must be >= 0")
        if settle_duration_s < 0.0:
            raise ValueError("settle_duration_s must be >= 0")

        self.sampling_duration_s = float(sampling_duration_s)
        self.settle_duration_s = float(settle_duration_s)
        self._time = time_source

        self._state = MissionState.IDLE
        self._route: Optional[Route] = None
        self._index = 0
        self._settle_start: Optional[float] = None
        self._sampling_start: Optional[float] = None
        self._resume_state: Optional[MissionState] = None
        self._events: List[StateEvent] = []

    # -- queries ---------------------------------------------------------
    @property
    def state(self) -> MissionState:
        return self._state

    @property
    def route(self) -> Optional[Route]:
        return self._route

    @property
    def current_waypoint_index(self) -> int:
        return self._index

    def current_waypoint(self) -> Optional[Waypoint]:
        if self._route is None:
            return None
        if self._index >= len(self._route.path):
            return None
        return self._route.path[self._index]

    @property
    def is_terminal(self) -> bool:
        return self._state in _TERMINAL

    @property
    def is_finished(self) -> bool:
        return self._state is MissionState.TASK_FINISHED

    def consume_events(self) -> List[StateEvent]:
        """Pop and return all pending events."""
        events = self._events
        self._events = []
        return events

    # -- state helpers ----------------------------------------------------
    def _set_state(self, state: MissionState) -> None:
        allowed = _TRANSITIONS.get(self._state, frozenset())
        if state not in allowed:
            raise RuntimeError(
                f"illegal transition {self._state.value} -> {state.value}"
            )
        self._state = state
        self._events.append(StateEvent(kind="state_changed", state=state))

    def _force_state(self, state: MissionState) -> None:
        """Set state without transition-table validation (stop/fault)."""
        self._state = state
        self._events.append(StateEvent(kind="state_changed", state=state))

    def _emit(self, kind: str, message: Optional[str] = None) -> None:
        wp = self.current_waypoint()
        self._events.append(
            StateEvent(
                kind=kind,
                state=self._state,
                waypoint_seq=wp.seq if wp is not None else None,
                sample_id=wp.sample_id if wp is not None else None,
                message=message,
            )
        )

    def _advance_waypoint(self) -> None:
        """Move to the next waypoint, or finish the task."""
        if self._route is None:
            raise RuntimeError("cannot advance without a loaded route")
        self._index += 1
        if self._index >= len(self._route.path):
            self._set_state(MissionState.TASK_FINISHED)
            self._emit("task_finished")
        else:
            self._set_state(MissionState.NAVIGATING)

    # -- public transitions ----------------------------------------------
    def load_route(self, route: Route) -> None:
        """IDLE -> TASK_LOADED."""
        if self._state is not MissionState.IDLE:
            raise RuntimeError(
                f"load_route only valid from IDLE, current {self._state.value}"
            )
        if not route.path:
            raise ValueError("route has no waypoints")
        self._route = route
        self._index = 0
        self._set_state(MissionState.TASK_LOADED)

    def start(self) -> None:
        """TASK_LOADED -> NAVIGATING."""
        if self._state is not MissionState.TASK_LOADED:
            raise RuntimeError(
                f"start only valid from TASK_LOADED, current {self._state.value}"
            )
        self._set_state(MissionState.NAVIGATING)

    def arrive_at_waypoint(self) -> None:
        """NAVIGATING/RETURNING -> ARRIVED (emits ``waypoint_arrived``)."""
        if self._state not in (MissionState.NAVIGATING, MissionState.RETURNING):
            raise RuntimeError(
                f"arrive_at_waypoint only valid from NAVIGATING/RETURNING, "
                f"current {self._state.value}"
            )
        self._set_state(MissionState.ARRIVED)
        self._emit("waypoint_arrived")

    def stop(self) -> None:
        """Any non-dead state -> STOPPED."""
        if self._state in _DEAD:
            return
        self._force_state(MissionState.STOPPED)
        self._emit("stopped")

    def pause(self) -> None:
        """Pause a moving task.  Resume always returns to a safe driving state."""
        if self._state not in (MissionState.NAVIGATING, MissionState.RETURNING):
            raise RuntimeError(f"pause only valid while moving, current {self._state.value}")
        self._resume_state = self._state
        self._set_state(MissionState.PAUSED)
        self._emit("paused")

    def resume(self) -> None:
        """Resume a paused task without changing its current waypoint."""
        if self._state is not MissionState.PAUSED:
            raise RuntimeError(f"resume only valid from PAUSED, current {self._state.value}")
        self._set_state(self._resume_state or MissionState.NAVIGATING)
        self._resume_state = None
        self._emit("resumed")

    def return_home(self) -> None:
        """Route the controller to the final return waypoint; this is not a physical e-stop."""
        if self._state is not MissionState.NAVIGATING or self._route is None:
            raise RuntimeError(f"return_home only valid from NAVIGATING, current {self._state.value}")
        self._index = len(self._route.path) - 1
        self._set_state(MissionState.RETURNING)
        self._emit("returning")

    def cancel(self) -> None:
        """Terminate a task by operator request; cannot be resumed."""
        if self._state in _DEAD or self._state is MissionState.TASK_FINISHED:
            return
        self._force_state(MissionState.STOPPED)
        self._emit("cancelled")

    def fault(self, reason: str) -> None:
        """Any non-dead state -> FAULT."""
        if self._state in _DEAD:
            return
        self._force_state(MissionState.FAULT)
        self._emit("fault", message=reason)

    # -- time-driven progression -----------------------------------------
    def advance(self, now: Optional[float] = None) -> None:
        """Advance exactly one transition based on the current state.

        Call repeatedly (once per control tick) to drive the machine forward.
        Timed states (SETTLING / SAMPLING) only progress once their dwell has
        elapsed; every intermediate state is observable between calls."""
        if now is None:
            now = self._time()
        state = self._state

        if state is MissionState.ARRIVED:
            self._set_state(MissionState.SETTLING)
            self._settle_start = now
        elif state is MissionState.SETTLING:
            start = self._settle_start if self._settle_start is not None else now
            if now - start >= self.settle_duration_s:
                wp = self.current_waypoint()
                if wp is not None and wp.is_sampling:
                    self._set_state(MissionState.SAMPLE_REQUESTED)
                else:
                    self._advance_waypoint()
        elif state is MissionState.SAMPLE_REQUESTED:
            self._set_state(MissionState.SAMPLING)
            self._sampling_start = now
            self._emit("sample_requested")
        elif state is MissionState.SAMPLING:
            start = self._sampling_start if self._sampling_start is not None else now
            if now - start >= self.sampling_duration_s:
                self._set_state(MissionState.SAMPLE_FINISHED)
                self._emit("sample_finished")
        elif state is MissionState.SAMPLE_FINISHED:
            self._advance_waypoint()


__all__ = [
    "MissionState",
    "StateEvent",
    "SamplingStateMachine",
]
