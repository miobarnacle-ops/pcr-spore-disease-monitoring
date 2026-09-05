"""Launch the ATGM336H GNSS adapter with a safe disabled default."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = Path(get_package_share_directory("spore_patrol_gnss"))
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "enabled",
                default_value="false",
                description="Open the GNSS serial device only when explicitly enabled.",
            ),
            DeclareLaunchArgument(
                "port",
                default_value="/dev/ttyUSB0",
                description="ATGM336H serial device.",
            ),
            DeclareLaunchArgument(
                "baud_rate",
                default_value="9600",
                description="ATGM336H NMEA baud rate.",
            ),
            Node(
                package="spore_patrol_gnss",
                executable="gnss_node",
                name="spore_patrol_gnss",
                output="screen",
                parameters=[
                    str(package_share / "config" / "atgm336h.yaml"),
                    {
                        "enabled": LaunchConfiguration("enabled"),
                        "port": LaunchConfiguration("port"),
                        "baud_rate": LaunchConfiguration("baud_rate"),
                    },
                ],
            ),
        ]
    )
