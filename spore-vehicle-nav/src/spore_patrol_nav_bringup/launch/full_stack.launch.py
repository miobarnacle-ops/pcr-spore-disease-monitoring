"""Safe stationary-capable hardware stack for the spore patrol vehicle.

This entry point owns the complete sensor/localization bring-up:
robot_state_publisher, the base feedback driver, YDLIDAR, local EKF and
SLAM Toolbox.  It intentionally does not start route tracking or publish
non-zero ``/cmd_vel`` commands.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    base_port = LaunchConfiguration("base_port")
    lidar_port = LaunchConfiguration("lidar_port")
    rviz = LaunchConfiguration("rviz")
    localization = LaunchConfiguration("localization")
    map_file_name = LaunchConfiguration("map_file_name")
    use_sim_time = LaunchConfiguration("use_sim_time")

    hardware_launch = PathJoinSubstitution(
        [
            FindPackageShare("spore_patrol_bringup"),
            "launch",
            "hardware.launch.py",
        ]
    )
    nav_launch = PathJoinSubstitution(
        [
            FindPackageShare("spore_patrol_nav_bringup"),
            "launch",
            "ekf_slam_bringup.launch.py",
        ]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "base_port",
                default_value="/dev/ttyACM0",
                description="STM32 base feedback serial device.",
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ydlidar",
                description="YDLIDAR serial device.",
            ),
            DeclareLaunchArgument(
                "rviz",
                default_value="false",
                description="Start RViz on the vehicle host.",
            ),
            DeclareLaunchArgument(
                "localization",
                default_value="false",
                description="Use SLAM Toolbox localization mode.",
            ),
            DeclareLaunchArgument(
                "map_file_name",
                default_value="",
                description="Serialized pose graph for localization mode.",
            ),
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="false",
                description="Use simulation time.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(hardware_launch),
                launch_arguments={
                    "port": base_port,
                    "lidar": "true",
                    "lidar_port": lidar_port,
                    "rviz": rviz,
                    # EKF owns odom -> base_footprint below.
                    "base_publish_tf": "false",
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav_launch),
                launch_arguments={
                    "use_sim_time": use_sim_time,
                    "localization": localization,
                    "map_file_name": map_file_name,
                    "start_base_driver": "false",
                    "start_lidar": "false",
                    "publish_tf": "true",
                }.items(),
            ),
        ]
    )
