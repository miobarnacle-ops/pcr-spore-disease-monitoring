from setuptools import setup

package_name = 'spore_patrol_nav_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=[],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [
            'launch/ekf_slam_bringup.launch.py',
            'launch/full_stack.launch.py',
        ]),
        ('share/' + package_name + '/config', ['config/local_ekf.yaml', 'config/slam_toolbox.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    author='vehicle-team',
    author_email='dev@example.com',
    maintainer='vehicle-team',
    maintainer_email='dev@example.com',
    description='Stage C bringup (EKF + SLAM) for spore patrol vehicle.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [],
    },
)
