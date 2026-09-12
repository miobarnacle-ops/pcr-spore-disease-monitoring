from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("cmd_vel_topic", default_value="/cmd_vel"),
            DeclareLaunchArgument("linear_speed_mps", default_value="0.05"),
            DeclareLaunchArgument("angular_speed_radps", default_value="0.15"),
            DeclareLaunchArgument("input_timeout_s", default_value="0.25"),
            Node(
                package="spore_patrol_teleop",
                executable="keyboard_teleop",
                name="spore_patrol_keyboard_teleop",
                output="screen",
                parameters=[
                    {
                        "cmd_vel_topic": LaunchConfiguration("cmd_vel_topic"),
                        "linear_speed_mps": LaunchConfiguration("linear_speed_mps"),
                        "angular_speed_radps": LaunchConfiguration(
                            "angular_speed_radps"
                        ),
                        "input_timeout_s": LaunchConfiguration("input_timeout_s"),
                    }
                ],
            ),
        ]
    )
