#!/usr/bin/env python3
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.substitutions import ThisLaunchFileDir

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def is_valid_to_launch():
    path = '/sys/firmware/devicetree/base/model'
    if os.path.exists(path):
        return False
    else:
        return True


def generate_launch_description():
    if not is_valid_to_launch():
        print('Can not launch fake robot in Raspberry Pi')
        return LaunchDescription([])

    start_rviz = LaunchConfiguration('start_rviz')
    prefix = LaunchConfiguration('prefix')
    use_sim = LaunchConfiguration('use_sim')

    # ワールドファイルのパス (SDFファイルに変更されている場合は拡張子を修正してください)
    world = LaunchConfiguration(
        'world',
        default=PathJoinSubstitution(
            [
                FindPackageShare('turtlebot3_lime_bringup'),
                'worlds',
                'turtlebot3_world.model' # ※新しいGazeboでは .sdf が推奨されます
            ]
        )
    )

    pose = {'x': LaunchConfiguration('x_pose', default='-2.00'),
            'y': LaunchConfiguration('y_pose', default='-0.50'),
            'z': LaunchConfiguration('z_pose', default='0.01'),
            'R': LaunchConfiguration('roll', default='0.00'),
            'P': LaunchConfiguration('pitch', default='0.00'),
            'Y': LaunchConfiguration('yaw', default='0.00')}

    return LaunchDescription([
        # --- (DeclareLaunchArgumentのブロックは元のコードと同じため省略・そのまま使用してください) ---
        # DeclareLaunchArgument('start_rviz', ...
        # ...
        # DeclareLaunchArgument('yaw', ...

        # 1. ロボット本体のLaunch (robot_state_publisherやコントローラの起動)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([ThisLaunchFileDir(), '/base.launch.py']),
            launch_arguments={
                'start_rviz': start_rviz,
                'prefix': prefix,
                'use_sim': use_sim,
            }.items(),
        ),

        # 2. 【変更】Gazebo Harmonic (ros_gz_sim) の起動
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                [PathJoinSubstitution([FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py'])]
            ),
            # -r オプションで起動直後からシミュレーションを再生 (一時停止しない)
            launch_arguments={'gz_args': ['-r ', world]}.items(),
        ),

        # 3. 【変更】モデルのスパウン (spawn_entity.py -> create)
        Node(
            package='ros_gz_sim',
            executable='create',
            arguments=[
                '-topic', 'robot_description',
                '-name', 'turtlebot3_lime_system',
                '-x', pose['x'], '-y', pose['y'], '-z', pose['z'],
                '-R', pose['R'], '-P', pose['P'], '-Y', pose['Y'],
            ],
            output='screen',
        ),

        # 4. 【新規追加】ROS 2とGazeboの時間を同期するブリッジ
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            arguments=[
                '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'
                '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            ],
            output='screen',
        ),
    ])