#!/usr/bin/env python3

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from moveit_configs_utils import MoveItConfigsBuilder

def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')

    description_pkg = 'turtlebot3_lime_description'
    moveit_config_pkg = 'turtlebot3_lime_moveit_config'

    # URDFの絶対パスを取得
    urdf_file = os.path.join(get_package_share_directory(description_pkg), 'urdf', 'standalone_sara.urdf.xacro')

    # ==========================================
    # 最強のツール「MoveItConfigsBuilder」を使用
    # ==========================================
    moveit_config = (
        MoveItConfigsBuilder(robot_name='open_manipulator_sara', package_name=moveit_config_pkg)
        # xacroの引数(mappings)もここで渡せます
        .robot_description(file_path=urdf_file, mappings={'use_sim': 'true'})
        .robot_description_semantic(file_path='config/standalone_sara.srdf')
        .trajectory_execution(file_path='config/moveit_controllers.yaml')
        .robot_description_kinematics(file_path='config/kinematics.yaml')
        .joint_limits(file_path='config/joint_limits.yaml')
        .planning_pipelines(pipelines=['ompl']) 
        .to_moveit_configs()
    )

    # Node: robot_state_publisher
    rsp_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='both',
        parameters=[moveit_config.robot_description, {'use_sim_time': use_sim_time}]
    )

    # Node: Gazebo Harmonic の起動
    gazebo_node = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [PathJoinSubstitution([FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py'])]
        ),
        launch_arguments={'gz_args': '-r empty.sdf'}.items(),
    )

    # Node: モデルをスパウン
    spawn_entity = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=['-topic', 'robot_description', '-name', 'open_manipulator_sara', '-z', '0.01'],
    )

    # Node: クロックのブリッジ
    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
        output='screen'
    )

    # Node: ros2_control コントローラの起動
    load_jsb = Node(package='controller_manager', executable='spawner', arguments=['joint_state_broadcaster'])
    load_arm = Node(package='controller_manager', executable='spawner', arguments=['arm_controller'])
    load_gripper = Node(package='controller_manager', executable='spawner', arguments=['gripper_controller'])

    # Node: MoveIt (move_group) の起動
    run_move_group_node = Node(
        package='moveit_ros_move_group',
        executable='move_group',
        output='screen',
        parameters=[
            moveit_config.to_dict(),
            {'use_sim_time': use_sim_time},
        ],
    )

    rviz_config_file = PathJoinSubstitution([FindPackageShare(moveit_config_pkg), 'config', 'moveit.rviz'])
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='log',
        # ↓ --ros-args と --log-level WARN を追加します
        arguments=['-d', rviz_config_file, '--ros-args', '--log-level', 'WARN'],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            {'use_sim_time': use_sim_time},
        ],
    )

    # イベントハンドラ: Gazeboの立ち上げ完了を待ってから順次起動
    delay_jsb = RegisterEventHandler(OnProcessExit(target_action=spawn_entity, on_exit=[load_jsb]))
    delay_ctrls = RegisterEventHandler(OnProcessExit(target_action=load_jsb, on_exit=[load_arm, load_gripper]))
    delay_moveit = RegisterEventHandler(OnProcessExit(target_action=load_arm, on_exit=[run_move_group_node, rviz_node]))

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true', description='Use simulation time'),
        rsp_node,
        gazebo_node,
        spawn_entity,
        clock_bridge,
        delay_jsb,
        delay_ctrls,
        delay_moveit
    ])