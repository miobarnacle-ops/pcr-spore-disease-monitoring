from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
import xacro


def generate_launch_description():
    description_share = Path(
        get_package_share_directory("spore_patrol_description")
    )
    sim_share = Path(get_package_share_directory("spore_patrol_sim"))
    gazebo_share = Path(get_package_share_directory("gazebo_ros"))

    robot_description = xacro.process_file(
        str(description_share / "urdf" / "spore_patrol_robot.urdf.xacro")
    ).toxml()
    use_rviz = LaunchConfiguration("rviz")
    use_gui = LaunchConfiguration("gui")
    use_slam = LaunchConfiguration("slam")
    use_sim_time = LaunchConfiguration("use_sim_time")
    world = LaunchConfiguration("world")
    spawn_x = LaunchConfiguration("spawn_x")
    spawn_y = LaunchConfiguration("spawn_y")
    spawn_yaw = LaunchConfiguration("spawn_yaw")
    slam_params_file = LaunchConfiguration("slam_params_file")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "rviz",
                default_value="true",
                description="Start RViz alongside Gazebo.",
            ),
            DeclareLaunchArgument(
                "gui",
                default_value="true",
                description="Start the Gazebo graphical client.",
            ),
            DeclareLaunchArgument(
                "slam",
                default_value="false",
                description=(
                    "Start SLAM Toolbox against simulated /scan and /odom. "
                    "No hardware driver or /cmd_vel is started."
                ),
            ),
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="true",
                description="Use Gazebo's /clock for robot and SLAM nodes.",
            ),
            DeclareLaunchArgument(
                "world",
                default_value=str(sim_share / "worlds" / "farmland_8x6.world"),
                description="SDF world file to load.",
            ),
            DeclareLaunchArgument(
                "spawn_x",
                default_value="-2.0",
                description="Initial robot x position in the field frame.",
            ),
            DeclareLaunchArgument(
                "spawn_y",
                default_value="-0.71",
                description="Initial robot y position in the field frame.",
            ),
            DeclareLaunchArgument(
                "spawn_yaw",
                default_value="0.0",
                description="Initial robot yaw in radians.",
            ),
            DeclareLaunchArgument(
                "slam_params_file",
                default_value=str(sim_share / "config" / "sim_mapping.yaml"),
                description="SLAM Toolbox parameter file.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(gazebo_share / "launch" / "gazebo.launch.py")
                ),
                launch_arguments={
                    "world": world,
                    "verbose": "false",
                    "gui": use_gui,
                }.items(),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        ),
                    }
                ],
            ),
            Node(
                package="gazebo_ros",
                executable="spawn_entity.py",
                arguments=[
                    "-topic",
                    "robot_description",
                    "-entity",
                    "spore_patrol_robot",
                    "-x",
                    spawn_x,
                    "-y",
                    spawn_y,
                    "-z",
                    "0.02",
                    "-Y",
                    spawn_yaw,
                ],
                output="screen",
            ),
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
                        )
                    },
                ],
                condition=IfCondition(use_slam),
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    str(description_share / "rviz" / "model.rviz"),
                ],
                parameters=[
                    {
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        )
                    }
                ],
                condition=IfCondition(use_rviz),
                output="screen",
            ),
        ]
    )
