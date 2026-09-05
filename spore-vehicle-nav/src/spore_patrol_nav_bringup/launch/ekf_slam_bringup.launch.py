"""Stage C bringup: robot_localization EKF + SLAM Toolbox.

Brings up the fused local odometry (odom -> base_footprint) and SLAM Toolbox
(map -> odom) for the spore patrol vehicle (WHEELTEC R550 PLUS / Raspberry Pi 5).

TF ownership (CONVENTIONS.md §1):
    map  -> odom            SLAM Toolbox (mapping or localization mode)
    odom -> base_footprint  robot_localization EKF
    base_footprint -> base_link -> laser_link   base driver / robot_state_publisher
There is exactly one publisher per transform.

Usage (mapping, Stage C):
    ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py
    # base driver + lidar already running, publishing /odom, /imu/data_raw,
    # /scan and the base_footprint -> base_link -> laser_link chain.

Usage (localization against a saved map):
    ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py \
        localization:=true map_file_name:=/home/pi/spore_patrol_ws/maps/field1

See README.md in this package for full instructions.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = Path(get_package_share_directory("spore_patrol_nav_bringup"))

    use_sim_time = LaunchConfiguration("use_sim_time")
    ekf_params_file = LaunchConfiguration("ekf_params_file")
    slam_params_file = LaunchConfiguration("slam_params_file")
    localization = LaunchConfiguration("localization")
    map_file_name = LaunchConfiguration("map_file_name")
    publish_tf = LaunchConfiguration("publish_tf")
    start_base_driver = LaunchConfiguration("start_base_driver")
    base_port = LaunchConfiguration("base_port")
    start_lidar = LaunchConfiguration("start_lidar")
    lidar_port = LaunchConfiguration("lidar_port")
    save_map = LaunchConfiguration("save_map")
    map_save_path = LaunchConfiguration("map_save_path")

    # Resolved lazily so that a missing spore_patrol_base_driver package does
    # not break the default launch (which assumes the base driver is already
    # running elsewhere).
    base_driver_launch = PathJoinSubstitution(
        [
            FindPackageShare("spore_patrol_base_driver"),
            "launch",
            "base_driver.launch.py",
        ]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="false",
                description="Use simulation clock instead of the host clock.",
            ),
            DeclareLaunchArgument(
                "ekf_params_file",
                default_value=str(package_share / "config" / "local_ekf.yaml"),
                description="robot_localization EKF parameter file.",
            ),
            DeclareLaunchArgument(
                "slam_params_file",
                default_value=str(package_share / "config" / "slam_toolbox.yaml"),
                description="SLAM Toolbox parameter file.",
            ),
            DeclareLaunchArgument(
                "localization",
                default_value="false",
                description=(
                    "Run SLAM Toolbox in localization mode against a saved "
                    "pose graph instead of mapping mode."
                ),
            ),
            DeclareLaunchArgument(
                "map_file_name",
                default_value="",
                description=(
                    "Pose graph file (extension omitted) to load in "
                    "localization mode. Required when localization:=true."
                ),
            ),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description="Let the EKF publish odom to base_footprint.",
            ),
            DeclareLaunchArgument(
                "start_base_driver",
                default_value="false",
                description=(
                    "Start the base driver (publishes /odom and /imu/data_raw). "
                    "Default false: assume it is already running."
                ),
            ),
            DeclareLaunchArgument(
                "base_port",
                default_value="/dev/ttyACM0",
                description="STM32 base driver serial device.",
            ),
            DeclareLaunchArgument(
                "start_lidar",
                default_value="false",
                description=(
                    "Start the YDLIDAR driver (publishes /scan). Default false: "
                    "assume it is already running."
                ),
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ydlidar",
                description="YDLIDAR serial device.",
            ),
            DeclareLaunchArgument(
                "save_map",
                default_value="false",
                description=(
                    "Save the current /map to disk (one-shot) and exit. "
                    "Prefer running map_saver_cli in a separate terminal while "
                    "mapping is still running; see README.md."
                ),
            ),
            DeclareLaunchArgument(
                "map_save_path",
                default_value=str(Path.home() / "spore_patrol_maps" / "map"),
                description="Output path (extension omitted) for the saved map.",
            ),

            # (a) Local EKF: odom -> base_footprint, output /odometry/filtered.
            Node(
                package="robot_localization",
                executable="ekf_node",
                name="ekf_local_filter_node",
                output="screen",
                parameters=[
                    ekf_params_file,
                    {
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        ),
                        "publish_tf": ParameterValue(
                            publish_tf,
                            value_type=bool,
                        ),
                    },
                ],
            ),

            # (b) SLAM Toolbox: map -> odom, mapping mode (default).
            Node(
                package="slam_toolbox",
                executable="async_slam_toolbox_node",
                name="slam_toolbox",
                output="screen",
                parameters=[
                    slam_params_file,
                    {
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        ),
                    },
                ],
                condition=UnlessCondition(localization),
            ),

            # (b') SLAM Toolbox: map -> odom, localization mode.
            Node(
                package="slam_toolbox",
                executable="localization_slam_toolbox_node",
                name="slam_toolbox",
                output="screen",
                parameters=[
                    slam_params_file,
                    {
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        ),
                        "mode": "localization",
                        "map_file_name": map_file_name,
                    },
                ],
                condition=IfCondition(localization),
            ),

            # (c) Optional base driver (odom + imu). publish_tf stays false so
            # the EKF remains the only publisher of odom -> base_footprint.
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(base_driver_launch),
                launch_arguments={
                    "port": base_port,
                    "publish_tf": "false",
                }.items(),
                condition=IfCondition(start_base_driver),
            ),

            # (c') Optional lidar (scan). Uses the driver's own defaults apart
            # from the port and the laser_link frame (CONVENTIONS.md §1).
            Node(
                package="ydlidar_ros2_driver",
                executable="ydlidar_ros2_driver_node",
                name="ydlidar_ros2_driver_node",
                output="screen",
                emulate_tty=True,
                parameters=[
                    {
                        "port": lidar_port,
                        "frame_id": "laser_link",
                    }
                ],
                condition=IfCondition(start_lidar),
            ),

            # (d) Optional map saver: one-shot pgm+yaml dump of the current
            # /map. See README.md for the recommended end-of-mapping workflow.
            Node(
                package="nav2_map_server",
                executable="map_saver_cli",
                name="map_saver",
                output="screen",
                arguments=["-f", map_save_path],
                parameters=[{"save_map_timeout": 60.0}],
                condition=IfCondition(save_map),
            ),
        ]
    )
