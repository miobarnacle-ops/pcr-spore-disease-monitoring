"""Launch the route tracker node (Stage D: route_v1.json -> Pure Pursuit)."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = Path(
        get_package_share_directory("spore_patrol_route_validation")
    )

    route_file = LaunchConfiguration("route_file")
    start_pose_x = LaunchConfiguration("start_pose_x")
    start_pose_y = LaunchConfiguration("start_pose_y")
    start_pose_yaw = LaunchConfiguration("start_pose_yaw")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "route_file",
                default_value="",
                description="Absolute path to route_v1.json.",
            ),
            DeclareLaunchArgument(
                "start_pose_x",
                default_value="0.0",
                description="Vehicle start pose x in map/odom frame (m).",
            ),
            DeclareLaunchArgument(
                "start_pose_y",
                default_value="0.0",
                description="Vehicle start pose y in map/odom frame (m).",
            ),
            DeclareLaunchArgument(
                "start_pose_yaw",
                default_value="0.0",
                description="Vehicle start pose yaw in map/odom frame (rad).",
            ),
            Node(
                package="spore_patrol_route_validation",
                executable="route_tracker",
                name="route_tracker",
                output="screen",
                parameters=[
                    str(package_share / "config" / "route_tracker.yaml"),
                    {
                        "route_file": route_file,
                        "start_pose_x": start_pose_x,
                        "start_pose_y": start_pose_y,
                        "start_pose_yaw": start_pose_yaw,
                    },
                ],
            ),
        ]
    )
