from glob import glob
import os

from setuptools import find_packages, setup


package_name = "spore_patrol_teleop"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test", "tests")),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml", "README.md"]),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Spore Patrol Team",
    maintainer_email="team@example.com",
    description="Minimal W/A/S/D ROS 2 keyboard teleoperation console.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "keyboard_teleop = spore_patrol_teleop.keyboard_teleop:main",
        ],
    },
)
