"""ROS 2 serial node for ATGM336H NMEA output.

The node is deliberately conservative: it defaults to ``enabled:=false``,
publishes ordinary autonomous fixes as ``single``, and never emits any
vehicle motion command.  Protocol and coordinate math live in sibling pure
modules and remain testable without a ROS installation or serial device.
"""

from __future__ import annotations

import json
import math
import os
import select
import termios
import time
from typing import Optional

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import PointStamped, Vector3Stamped
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import Float32, String

from .enu import EnuOrigin, geodetic_to_enu
from .nmea_parser import NmeaParseError, NmeaPosition, NmeaVelocity, parse_nmea_sentence


BAUD_RATES = {
    4800: termios.B4800,
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


class Atgm336hNode(Node):
    """NMEA serial reader and ROS 2 message adapter."""

    def __init__(self) -> None:
        super().__init__("spore_patrol_gnss")
        self.declare_parameter("enabled", False)
        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baud_rate", 9600)
        self.declare_parameter("frame_id", "gnss_link")
        self.declare_parameter("poll_rate_hz", 50.0)
        self.declare_parameter("fix_timeout_s", 2.0)
        self.declare_parameter("require_checksum", False)
        self.declare_parameter("single_fix_std_m", 5.0)
        self.declare_parameter("fix_topic", "/fix")
        self.declare_parameter("velocity_topic", "/gps/velocity")
        self.declare_parameter("speed_topic", "/gps/speed_mps")
        self.declare_parameter("course_topic", "/gps/course_deg")
        self.declare_parameter("raw_topic", "/gps/raw_nmea")
        self.declare_parameter("status_topic", "/gps/status")
        self.declare_parameter("diagnostics_topic", "/gps/diagnostics")
        self.declare_parameter("enu_topic", "/gps/enu")
        self.declare_parameter("publish_enu", False)
        self.declare_parameter("enu_frame_id", "field")
        self.declare_parameter("origin_latitude_deg", 0.0)
        self.declare_parameter("origin_longitude_deg", 0.0)
        self.declare_parameter("origin_altitude_m", 0.0)

        self.enabled = bool(self.get_parameter("enabled").value)
        self.port = str(self.get_parameter("port").value)
        self.baud_rate = int(self.get_parameter("baud_rate").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.fix_timeout_s = float(self.get_parameter("fix_timeout_s").value)
        self.require_checksum = bool(self.get_parameter("require_checksum").value)
        self.single_fix_std_m = float(self.get_parameter("single_fix_std_m").value)
        self.publish_enu = bool(self.get_parameter("publish_enu").value)
        self.serial_fd: Optional[int] = None
        self.read_buffer = ""
        self.last_position: Optional[NmeaPosition] = None
        self.last_velocity: Optional[NmeaVelocity] = None
        self.last_position_monotonic: Optional[float] = None
        self.last_rx_monotonic: Optional[float] = None
        self.last_error: Optional[str] = None
        self.parse_error_count = 0
        self.serial_error_count = 0
        self.retry_after_monotonic = 0.0

        self.fix_publisher = self.create_publisher(NavSatFix, str(self.get_parameter("fix_topic").value), 10)
        self.velocity_publisher = self.create_publisher(Vector3Stamped, str(self.get_parameter("velocity_topic").value), 10)
        self.speed_publisher = self.create_publisher(Float32, str(self.get_parameter("speed_topic").value), 10)
        self.course_publisher = self.create_publisher(Float32, str(self.get_parameter("course_topic").value), 10)
        self.raw_publisher = self.create_publisher(String, str(self.get_parameter("raw_topic").value), 20)
        self.status_publisher = self.create_publisher(String, str(self.get_parameter("status_topic").value), 10)
        self.diagnostics_publisher = self.create_publisher(DiagnosticArray, str(self.get_parameter("diagnostics_topic").value), 10)
        self.enu_publisher = self.create_publisher(PointStamped, str(self.get_parameter("enu_topic").value), 10)

        self.origin: Optional[EnuOrigin] = None
        if self.publish_enu:
            try:
                self.origin = EnuOrigin(
                    float(self.get_parameter("origin_latitude_deg").value),
                    float(self.get_parameter("origin_longitude_deg").value),
                    float(self.get_parameter("origin_altitude_m").value),
                    str(self.get_parameter("enu_frame_id").value),
                )
            except ValueError as error:
                self.get_logger().error(f"ENU disabled because origin is invalid: {error}")
                self.publish_enu = False

        poll_rate_hz = max(1.0, float(self.get_parameter("poll_rate_hz").value))
        self.poll_timer = self.create_timer(1.0 / poll_rate_hz, self._poll_serial)
        self.diagnostics_timer = self.create_timer(1.0, self._publish_diagnostics)
        self.get_logger().info(
            f"ATGM336H NMEA adapter ready: enabled={self.enabled}, port={self.port}, baud={self.baud_rate}; "
            "ordinary GNSS is reported as single, not RTK fix"
        )

    def _open_serial(self) -> None:
        if self.serial_fd is not None or not self.enabled or time.monotonic() < self.retry_after_monotonic:
            return
        speed = BAUD_RATES.get(self.baud_rate)
        if speed is None:
            self.last_error = f"unsupported baud rate: {self.baud_rate}"
            self.retry_after_monotonic = time.monotonic() + 5.0
            return
        try:
            fd = os.open(self.port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
            attrs = termios.tcgetattr(fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
            attrs[3] = 0
            attrs[4] = speed
            attrs[5] = speed
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            self.serial_fd = fd
            self.last_error = None
            self.get_logger().info(f"opened GNSS serial port {self.port} at {self.baud_rate} baud")
        except (OSError, termios.error) as error:
            self.serial_error_count += 1
            self.last_error = f"serial open failed: {error}"
            self.retry_after_monotonic = time.monotonic() + 2.0

    def _close_serial(self) -> None:
        if self.serial_fd is None:
            return
        try:
            os.close(self.serial_fd)
        except OSError:
            pass
        self.serial_fd = None

    def _poll_serial(self) -> None:
        if not self.enabled:
            return
        self._open_serial()
        if self.serial_fd is None:
            return
        try:
            ready, _, _ = select.select([self.serial_fd], [], [], 0.0)
            if not ready:
                return
            self.read_buffer += os.read(self.serial_fd, 4096).decode("ascii", errors="replace")
        except (OSError, ValueError) as error:
            self.serial_error_count += 1
            self.last_error = f"serial read failed: {error}"
            self._close_serial()
            self.retry_after_monotonic = time.monotonic() + 2.0
            return
        lines = self.read_buffer.split("\n")
        self.read_buffer = lines.pop()[-8192:]
        for line in lines:
            self._handle_sentence(line.strip())

    def _handle_sentence(self, sentence: str) -> None:
        if not sentence:
            return
        self.last_rx_monotonic = time.monotonic()
        raw_message = String()
        raw_message.data = sentence
        self.raw_publisher.publish(raw_message)
        try:
            record = parse_nmea_sentence(sentence, require_checksum=self.require_checksum)
        except NmeaParseError as error:
            self.parse_error_count += 1
            self.last_error = str(error)
            return
        self.last_error = None
        if isinstance(record, NmeaPosition):
            self._publish_position(record)
        elif isinstance(record, NmeaVelocity):
            self._publish_velocity(record)

    def _publish_position(self, position: NmeaPosition) -> None:
        self.last_position = position
        self.last_position_monotonic = time.monotonic()
        stamp = self.get_clock().now().to_msg()
        message = NavSatFix()
        message.header.stamp = stamp
        message.header.frame_id = self.frame_id
        message.status.status = NavSatStatus.STATUS_FIX if position.valid else NavSatStatus.STATUS_NO_FIX
        message.status.service = NavSatStatus.SERVICE_GPS
        message.latitude = position.latitude_deg if position.latitude_deg is not None else math.nan
        message.longitude = position.longitude_deg if position.longitude_deg is not None else math.nan
        message.altitude = position.altitude_m if position.altitude_m is not None else math.nan
        if position.valid:
            variance = max(0.1, self.single_fix_std_m) ** 2
            message.position_covariance = [variance, 0.0, 0.0, 0.0, variance, 0.0, 0.0, 0.0, variance * 4.0]
            message.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        else:
            message.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.fix_publisher.publish(message)
        if position.valid and self.publish_enu and self.origin is not None and position.altitude_m is not None:
            east, north, up = geodetic_to_enu(position.latitude_deg, position.longitude_deg, position.altitude_m, self.origin)
            enu = PointStamped()
            enu.header.stamp = stamp
            enu.header.frame_id = self.origin.frame_id
            enu.point.x, enu.point.y, enu.point.z = east, north, up
            self.enu_publisher.publish(enu)
        self._publish_status()

    def _publish_velocity(self, velocity: NmeaVelocity) -> None:
        self.last_velocity = velocity
        stamp = self.get_clock().now().to_msg()
        vector = Vector3Stamped()
        vector.header.stamp = stamp
        vector.header.frame_id = self.frame_id
        vector.vector.x = velocity.speed_mps or 0.0
        vector.vector.y = velocity.course_deg or 0.0
        vector.vector.z = velocity.speed_kmh or 0.0
        self.velocity_publisher.publish(vector)
        if velocity.speed_mps is not None:
            speed = Float32()
            speed.data = velocity.speed_mps
            self.speed_publisher.publish(speed)
        if velocity.course_deg is not None:
            course = Float32()
            course.data = velocity.course_deg
            self.course_publisher.publish(course)
        self._publish_status()

    def _publish_status(self) -> None:
        position = self.last_position
        payload = {
            "source": "ATGM336H",
            "protocol": "NMEA-0183",
            "quality": position.quality if position is not None else "unavailable",
            "fix_valid": bool(position is not None and position.valid),
            "satellites": position.satellites if position is not None else None,
            "hdop": position.hdop if position is not None else None,
            "timestamp_ms": int(time.time() * 1000),
            "enu_available": bool(self.publish_enu and self.origin is not None),
            "parse_error_count": self.parse_error_count,
        }
        message = String()
        message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.status_publisher.publish(message)

    def _publish_diagnostics(self) -> None:
        now = time.monotonic()
        status = DiagnosticStatus()
        status.name = "spore_patrol_gnss/ATGM336H"
        if not self.enabled:
            status.level = DiagnosticStatus.WARN
            status.message = "DISABLED: serial port is not opened"
        elif self.serial_fd is None:
            status.level = DiagnosticStatus.ERROR
            status.message = self.last_error or "serial port unavailable"
        elif self.last_position_monotonic is None or now - self.last_position_monotonic > self.fix_timeout_s:
            status.level = DiagnosticStatus.WARN
            status.message = "WAITING_FOR_FRESH_FIX"
        elif not self.last_position.valid:
            status.level = DiagnosticStatus.WARN
            status.message = "NO_FIX"
        else:
            status.level = DiagnosticStatus.OK
            status.message = "OK_SINGLE_GNSS"
        status.values = [
            KeyValue(key="port", value=self.port),
            KeyValue(key="baud_rate", value=str(self.baud_rate)),
            KeyValue(key="quality", value=self.last_position.quality if self.last_position else "unavailable"),
            KeyValue(key="parse_errors", value=str(self.parse_error_count)),
            KeyValue(key="serial_errors", value=str(self.serial_error_count)),
        ]
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        array.status = [status]
        self.diagnostics_publisher.publish(array)
        self._publish_status()

    def destroy_node(self):  # type: ignore[no-untyped-def]
        self._close_serial()
        return super().destroy_node()


def main(args=None):  # type: ignore[no-untyped-def]
    rclpy.init(args=args)
    node = Atgm336hNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


__all__ = ["Atgm336hNode", "main"]
