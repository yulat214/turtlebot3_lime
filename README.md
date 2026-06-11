# TurtleBot3 Lime — Jazzy / Ignition Gazebo

> **ブランチ:** `jazzy-devel` (ROS 2 Jazzy + Ignition Gazebo Harmonic)
> **ベース:** `humble-devel` (ROS 2 Humble + Classic Gazebo) からの移植

---

## 動作確認済み機能（2026-06-11 時点）

| 機能 | 状態 | 起動コマンド |
|------|------|-------------|
| Ignition Gazebo シミュレーション | ✅ | `gazebo.launch.py` |
| MoveIt 2 アーム制御 (joint1–6) | ✅ | `moveit_gazebo.launch.py` |
| グリッパー開閉 (gripper_left/right) | ✅ | 上記に含む |
| SLAM マッピング | ✅ | `slam_toolbox` 等 |
| Navigation2 自律ナビゲーション | ✅ | `navigation2_use_sim_time.launch.py` |
| MoveIt + Navigation2 統合 | ✅ | `moveit_navigation_use_sim_time.launch.py` |

---

## 起動コマンド一覧

### 1. Gazebo シミュレーション単体
```bash
ros2 launch turtlebot3_lime_bringup gazebo.launch.py
```

### 2. MoveIt 2（Gazebo + MoveIt）
```bash
ros2 launch turtlebot3_lime_moveit_config moveit_gazebo.launch.py
```

### 3. Navigation2（Gazebo を別途起動後）
```bash
ros2 launch turtlebot3_lime_bringup gazebo.launch.py
ros2 launch turtlebot3_lime_navigation2 navigation2_use_sim_time.launch.py \
  map_yaml_file:=$HOME/map.yaml
```

### 4. MoveIt + Navigation2 統合（推奨）
```bash
ros2 launch turtlebot3_lime_bringup gazebo.launch.py
ros2 launch turtlebot3_lime_bringup moveit_navigation_use_sim_time.launch.py \
  map_yaml_file:=$HOME/map.yaml
```

> **Note:** RViz は MoveIt 用と Navigation2 用の 2 ウィンドウが起動します。
> ログレベルは WARN に設定済みのため INFO スパムは非表示です。
> デバッグ時は `log_level:=INFO` を追加してください。

---

## セットアップ（新規 PC への移植）

```bash
# 1. ワークスペースにクローン
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src
git clone -b jazzy-devel https://github.com/<your-repo>/turtlebot3_lime.git

# 2. 依存関係インストール
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -y

# 3. 追加パッケージ（rosdep 未対応の場合）
sudo apt install \
  ros-jazzy-gz-ros2-control \
  ros-jazzy-ros-gz-sim \
  ros-jazzy-ros-gz-bridge \
  ros-jazzy-ros-gz-image \
  ros-jazzy-navigation2 \
  ros-jazzy-opennav-docking \
  ros-jazzy-moveit

# 4. ビルド
colcon build --symlink-install
source install/setup.bash
```

---

## Humble → Jazzy 移植の主要変更点

### Gazebo
- Classic Gazebo → Ignition Gazebo (Harmonic)
- プラグイン: `gazebo_ros2_control` → `gz_ros2_control/GazeboSimSystem`
- ブリッジ: `ros_gz_bridge` で clock / odom / tf / scan / cmd_vel / camera を接続
- world ファイルを Ignition SDF 形式に更新

### グリッパー
- command interface: `effort` → `position`
- コントローラー: `position_controllers/GripperActionController`
- URDF: `<dynamics friction="...">` 除去（DART が毎ステップ関節をリセットしていた根本原因）
- ros2_control: gripper_right_joint に `<param name="mimic">` で追従

### MoveIt 2
- OMPL パイプラインを Jazzy API に対応
- `allowed_goal_duration_margin: 2.0`（グリッパー stall 検知考慮）
- acceleration limits を `robot_description_planning` namespace に移動

### Navigation2（Jazzy Nav2 1.3.x 対応）

| 変更箇所 | Humble | Jazzy |
|----------|--------|-------|
| bt_navigator プラグイン | `plugin_lib_names` リスト | `navigators` 構造体 |
| controller_server | `progress_checker_plugin` | `progress_checker_plugins` |
| behavior_server プラグイン | `nav2_behaviors/Spin` | `nav2_behaviors::Spin` |
| planner_server プラグイン | `nav2_navfn_planner/NavfnPlanner` | `nav2_navfn_planner::NavfnPlanner` |
| 新規ライフサイクルノード | なし | `collision_monitor`, `docking_server` |
| launch 引数 | `default_bt_xml_filename` | 廃止（自動選択） |

---

## Future Work

### グリッパー把持シミュレーション
現在の position command interface (JointPositionReset) ではグリッパーが物体をすり抜ける。

**推奨実装:** `gz-sim-detachable-joint-system`
- 接触検知時にグリッパーリンクと物体の間に固定ジョイントを動的生成
- 参考: [gz-sim DetachableJoint](https://gazebosim.org/api/sim/8/classignition_1_1gazebo_1_1systems_1_1DetachableJoint.html)

```xml
<plugin filename="gz-sim-detachable-joint-system" name="gz::sim::systems::DetachableJoint">
  <parent_link>gripper_left_link</parent_link>
  <child_model>target_object</child_model>
  <child_link>link</child_link>
  <detach_topic>/detach</detach_topic>
</plugin>
```

### 実機（TurtleBot3 BigWheel Orin）対応確認
- `turtlebot3_lime_hardware` パッケージとの結合テスト
- 実機では `hardware.launch.py` を使用（Gazebo 不使用）

---

## 既知の制限・注意事項

- Ignition Gazebo (DART 物理エンジン) は SDF `<mimic>` 拘束を**サポートしない**
  → gripper_right_joint の追従は ros2_control の mimic param で実現
- グリッパーは視覚的開閉のみ。物体把持の物理シミュレーションは未実装（Future Work）
- RViz で `Message Filter dropping message: frame 'odom'` が出るがナビゲーション本体には無影響（シムタイム由来の TF タイミング差）

---

## セットアップ手順（詳細）

[セットアップ手順（Quick Start Guide）](./turtlebot3_lime/documentation/tb3_lime_setup.md)

## 参考リンク

- [ROBOTIS e-Manual for OpenManipulator with TurtleBot3](http://emanual.robotis.com/docs/en/platform/turtlebot3/manipulation/#manipulation)
- [open_manipulator (Jazzy)](https://github.com/ROBOTIS-GIT/open_manipulator)
- [nav2_bringup](https://github.com/ros-navigation/navigation2/tree/main/nav2_bringup)
