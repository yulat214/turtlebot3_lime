#!/usr/bin/env python3
#
# Copyright 2022 ROBOTIS CO., LTD.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author: Darby Lim (rewritten for Ignition Gazebo / Jazzy)

import os
import subprocess
import tempfile
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.actions import RegisterEventHandler
from launch.actions import TimerAction
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node


def _generate_gz_cm_yaml(bringup_dir, description_dir):
    """
    Generate a temp controller_manager YAML that includes robot_description.
    gz_ros2_control reads robot_description from the CM params to initialize
    GazeboSimSystem (the <ros2_control> section is dropped in URDF→SDF conversion).
    """
    xacro_file = os.path.join(description_dir, 'urdf', 'turtlebot3_lime.urdf.xacro')
    base_yaml_file = os.path.join(bringup_dir, 'config', 'gazebo_controller_manager.yaml')

    # Generate URDF string (use_sim=true, default prefix)
    urdf_result = subprocess.run(
        ['xacro', xacro_file, 'use_sim:=true', 'prefix:='],
        capture_output=True, text=True, check=True
    )
    urdf_string = urdf_result.stdout

    # Load base YAML and inject robot_description
    with open(base_yaml_file) as f:
        cm_params = yaml.safe_load(f)

    cm_params.setdefault('controller_manager', {}).setdefault('ros__parameters', {})
    cm_params['controller_manager']['ros__parameters']['robot_description'] = urdf_string

    # Write to a persistent temp file (not deleted on close so Gazebo can read it)
    tmp = tempfile.NamedTemporaryFile(
        delete=False, mode='w', suffix='_gz_cm.yaml',
        prefix='turtlebot3_lime_'
    )
    yaml.dump(cm_params, tmp, default_flow_style=False, allow_unicode=True)
    tmp.flush()
    return tmp.name


def generate_launch_description():
    bringup_dir = get_package_share_directory('turtlebot3_lime_bringup')
    description_dir = get_package_share_directory('turtlebot3_lime_description')
    ros_gz_sim_dir = get_package_share_directory('ros_gz_sim')

    # Generate CM YAML with robot_description so gz_ros2_control / GazeboSimSystem
    # can find the <ros2_control> hardware section (dropped during URDF→SDF conversion).
    gz_cm_yaml_path = _generate_gz_cm_yaml(bringup_dir, description_dir)

    start_rviz = LaunchConfiguration('start_rviz')
    prefix = LaunchConfiguration('prefix')

    world = LaunchConfiguration(
        'world',
        default=os.path.join(bringup_dir, 'worlds', 'turtlebot3_world.world')
    )

    x_pose = LaunchConfiguration('x_pose', default='-2.00')
    y_pose = LaunchConfiguration('y_pose', default='-0.50')
    z_pose = LaunchConfiguration('z_pose', default='0.01')
    roll  = LaunchConfiguration('roll',  default='0.00')
    pitch = LaunchConfiguration('pitch', default='0.00')
    yaw   = LaunchConfiguration('yaw',   default='0.00')

    bridge_params = os.path.join(bringup_dir, 'params', 'turtlebot3_lime_bridge.yaml')

    # --- base.launch.py: robot_state_publisher (use_sim=true, spawners disabled) ---
    # gz_cm_yaml_path is passed so the URDF xacro embeds the correct CM YAML path,
    # which now includes robot_description for gz_ros2_control initialization.
    base_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, 'launch', 'base.launch.py')
        ),
        launch_arguments={
            'start_rviz': start_rviz,
            'prefix': prefix,
            'use_sim': 'true',
            'gz_cm_yaml_path': gz_cm_yaml_path,
        }.items(),
    )

    # --- Ignition Gazebo server ---
    gz_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim_dir, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': ['-r -s -v4 ', world],
            'on_exit_shutdown': 'true',
        }.items(),
    )

    # --- Ignition Gazebo GUI client ---
    gz_gui = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim_dir, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': '-g -v2',
            'on_exit_shutdown': 'true',
        }.items(),
    )

    # Add worlds dir to GZ_SIM_RESOURCE_PATH so model://turtlebot3_world resolves
    set_gz_resource_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(bringup_dir, 'worlds')
    )

    # ros_gz_sim converts package://pkg/... → model://pkg/... when spawning URDF.
    # Add every AMENT_PREFIX_PATH entry's share/ so model:// URIs resolve for all packages
    # (covers turtlebot3_lime_description in workspace AND realsense2_description in /opt/ros).
    gz_mesh_paths = ':'.join(
        os.path.join(p, 'share')
        for p in os.environ.get('AMENT_PREFIX_PATH', '').split(':')
        if p
    )
    set_gz_description_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        gz_mesh_paths
    )

    # --- Spawn robot from /robot_description topic ---
    gz_spawn = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-topic', 'robot_description',
            '-name', 'turtlebot3_lime',
            '-allow_renaming', 'true',
            '-x', x_pose,
            '-y', y_pose,
            '-z', z_pose,
            '-R', roll,
            '-P', pitch,
            '-Y', yaw,
        ],
        output='screen',
    )

    # --- ros_gz_bridge: clock / odom / tf / cmd_vel / imu / scan / camera_info / points ---
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '--ros-args',
            '-p', f'config_file:={bridge_params}',
        ],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )

    # --- ros_gz_image: camera color and depth images ---
    image_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        arguments=['camera/camera/image', 'camera/camera/depth_image'],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )

    # --- Controller spawners (sim mode, sequential) ---
    # Run sequentially to avoid racing gz_ros2_control's own controller loading.
    # Chain: gz_spawn exits → 5s delay → JSB → arm → gripper
    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['joint_state_broadcaster', '-c', '/controller_manager'],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )
    arm_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['arm_controller', '-c', '/controller_manager'],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )
    gripper_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['gripper_controller', '-c', '/controller_manager'],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )

    # Sequential chaining: each spawner starts only after the previous one finishes.
    start_arm_after_jsb = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[arm_controller_spawner],
        )
    )
    start_gripper_after_arm = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=arm_controller_spawner,
            on_exit=[gripper_controller_spawner],
        )
    )
    # Start JSB 5 s after gz_spawn exits (gives gz_ros2_control time to init hardware).
    start_controllers_after_spawn = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=gz_spawn,
            on_exit=[
                TimerAction(
                    period=5.0,
                    actions=[joint_state_broadcaster_spawner],
                )
            ],
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'start_rviz',
            default_value='false',
            description='Whether to launch RViz2'),

        DeclareLaunchArgument(
            'prefix',
            default_value='""',
            description='Prefix of the joint and link names'),

        DeclareLaunchArgument(
            'world',
            default_value=world,
            description='Path to the Ignition Gazebo world file (.world / .sdf)'),

        DeclareLaunchArgument(
            'x_pose', default_value=x_pose, description='Spawn X position'),
        DeclareLaunchArgument(
            'y_pose', default_value=y_pose, description='Spawn Y position'),
        DeclareLaunchArgument(
            'z_pose', default_value=z_pose, description='Spawn Z position'),
        DeclareLaunchArgument(
            'roll',   default_value=roll,   description='Spawn roll'),
        DeclareLaunchArgument(
            'pitch',  default_value=pitch,  description='Spawn pitch'),
        DeclareLaunchArgument(
            'yaw',    default_value=yaw,    description='Spawn yaw'),

        set_gz_resource_path,
        set_gz_description_path,
        gz_server,
        gz_gui,
        base_launch,
        gz_spawn,
        bridge,
        image_bridge,
        start_controllers_after_spawn,
        start_arm_after_jsb,
        start_gripper_after_arm,
    ])
