"""spore_patrol_route_validation — vehicle-side adapter for route_v1.json.

Stage D of the spore-vehicle-nav subsystem: turn a web-exported ``route_v1.json``
task file into Pure Pursuit path tracking commands for the vehicle.

Input
-----
- ``route_v1.json`` task file (``field``/``local_enu``, metres), parsed and
  validated by :mod:`.route_model`.
- Vehicle pose from ROS odometry (``/odometry/filtered``, fallback ``/odom``),
  consumed only by the rclpy node :mod:`.route_tracker_node`.

Output
------
- ``/cmd_vel`` (``geometry_msgs/Twist``) at >= 5 Hz, zero when stopped (the
  base_driver has a 0.30 s ``cmd_vel`` watchdog).
- ``/mission/status`` (``std_msgs/String`` JSON) on state transitions and
  sampling events.

Pipeline
--------
``route_v1.json`` -> parse/validate (:mod:`.route_model`) -> field->map transform
(:mod:`.field_map_transform`) -> smooth + equal-arc resample
(:mod:`.path_smoothing`) -> Pure Pursuit tracking (:mod:`.pure_pursuit`) driven
by the sampling state machine (:mod:`.sampling_state_machine`).

Completion criteria
-------------------
- A route is accepted only if it passes full schema validation (no missing
  fields, no out-of-range speed, no negative tolerance).
- Tracking converges to each waypoint within its ``tolerance_m``, honouring the
  ~0.5 m minimum turn radius and the speed/angular limits.
- The mission reaches ``TASK_FINISHED`` after the final waypoint; each
  ``sampling`` waypoint is held for a 2 s dwell (simulated sampling) before the
  ``sample_finished`` event fires.

All pure-logic modules are importable and unit-testable without a ROS runtime
(``python3 -m pytest tests/ -q``); only :mod:`.route_tracker_node` imports
``rclpy``.
"""

from .route_model import (
    MAX_SPEED_LIMIT_MPS,
    Route,
    SCHEMA_VERSION,
    Waypoint,
    load_route,
    parse_route,
)
from .field_map_transform import (
    StartPose,
    field_to_map,
    field_to_map_xy,
    map_yaw,
    transform_route,
    transform_waypoint,
)
from .pure_pursuit import Pose, PurePursuitController, Twist
from .sampling_state_machine import (
    MissionState,
    SamplingStateMachine,
    StateEvent,
)
from .mission_contract import MissionStatus, is_fresh, parse_mission_status

__version__ = "0.1.0"

__all__ = [
    "MAX_SPEED_LIMIT_MPS",
    "SCHEMA_VERSION",
    "Route",
    "Waypoint",
    "parse_route",
    "load_route",
    "StartPose",
    "field_to_map",
    "field_to_map_xy",
    "map_yaw",
    "transform_route",
    "transform_waypoint",
    "Pose",
    "Twist",
    "PurePursuitController",
    "MissionState",
    "StateEvent",
    "SamplingStateMachine",
    "MissionStatus",
    "parse_mission_status",
    "is_fresh",
    "__version__",
]
