"""
Gazebo Multi-UAV Swarm Scenario Generator & World Provisioner.
Generates SDF worlds and multi-instance orchestration scripts for ArduPilot and PX4 SITL.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import os
from typing import Dict, List, Optional


class GazeboScenarioGenerator:
    """
    Provisions high-fidelity simulation environments for Gazebo Harmonic & Classic.
    Generates defense sector SDF worlds and multi-vehicle orchestration profiles.
    """

    @staticmethod
    def generate_defense_sector_sdf(
        base_name: str = "Apex_Forward_Operating_Base",
        hel_turret_pos: tuple = (0.0, 0.0, 1.5),
        radar_tower_pos: tuple = (-20.0, 10.0, 5.0),
    ) -> str:
        """
        Generates clean Gazebo SDF 1.9 world definition for C-UAS demonstration.
        """
        return f"""<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="{base_name}">
    <physics name="1ms" type="dart">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <!-- Sun Lighting -->
    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 100 0 0 0</pose>
      <diffuse>0.9 0.9 0.9 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <!-- Terrain Ground Plane -->
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>5000 5000</size>
            </plane>
          </geometry>
        </collision>
        <visual name="visual">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>5000 5000</size>
            </plane>
          </geometry>
          <material>
            <ambient>0.3 0.3 0.3 1</ambient>
            <diffuse>0.5 0.5 0.5 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

    <!-- High-Energy Laser (HEL) Turret Model -->
    <model name="apex_hel_turret">
      <static>false</static>
      <pose>{hel_turret_pos[0]} {hel_turret_pos[1]} {hel_turret_pos[2]} 0 0 0</pose>
      <link name="base_pedestal">
        <visual name="pedestal_vis">
          <geometry>
            <cylinder>
              <radius>0.8</radius>
              <length>2.0</length>
            </cylinder>
          </geometry>
          <material>
            <ambient>0.1 0.1 0.12 1</ambient>
            <diffuse>0.2 0.2 0.25 1</diffuse>
          </material>
        </visual>
      </link>
      <link name="optical_director">
        <pose>0 0 1.2 0 0 0</pose>
        <visual name="director_vis">
          <geometry>
            <sphere>
              <radius>0.5</radius>
            </sphere>
          </geometry>
          <material>
            <ambient>0.2 0.2 0.2 1</ambient>
            <diffuse>0.4 0.4 0.4 1</diffuse>
          </material>
        </visual>
      </link>
      <joint name="azimuth_joint" type="revolute">
        <parent>base_pedestal</parent>
        <child>optical_director</child>
        <axis>
          <xyz>0 0 1</xyz>
          <limit>
            <lower>-3.14159</lower>
            <upper>3.14159</upper>
          </limit>
        </axis>
      </joint>
    </model>

    <!-- Phased Array AESA Radar Mast -->
    <model name="aesa_radar_mast">
      <static>true</static>
      <pose>{radar_tower_pos[0]} {radar_tower_pos[1]} {radar_tower_pos[2]} 0 0 0</pose>
      <link name="mast_link">
        <visual name="mast_vis">
          <geometry>
            <box>
              <size>1.5 1.5 10.0</size>
            </box>
          </geometry>
          <material>
            <ambient>0.15 0.15 0.15 1</ambient>
            <diffuse>0.3 0.3 0.3 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

  </world>
</sdf>
"""

    @staticmethod
    def generate_ardupilot_swarm_runscript(
        num_drones: int = 5,
        target_speed_mps: float = 35.0,
    ) -> str:
        """
        Generates bash script to spawn multi-vehicle ArduPilot SITL instances with Gazebo Iris frames.
        """
        lines = [
            "#!/usr/bin/env bash",
            "# Apex-HiveMind ArduPilot SITL Multi-UAV Swarm Launcher",
            "set -e",
            "",
            "SCRIPT_DIR=$(dirname \"$0\")",
            f"echo \"Starting {num_drones} ArduCopter SITL Swarm Instances for Gazebo...\"",
            "",
        ]

        for i in range(1, num_drones + 1):
            sysid = i
            base_port = 5760 + (i * 10)
            mavlink_port = 14550 + i
            lines.append(f"# Instance {i} (SYSID {sysid})")
            lines.append(
                f"sim_vehicle.py -v ArduCopter -f gazebo-iris -I {i} --sysid {sysid} "
                f"--out 127.0.0.1:{mavlink_port} &"
            )

        lines.extend([
            "",
            "echo \"All SITL nodes active. Ingesting via Apex-HiveMind SITL Gateway.\"",
            "wait",
        ])
        return "\n".join(lines)

    @staticmethod
    def generate_px4_swarm_runscript(num_drones: int = 5) -> str:
        """
        Generates bash script for PX4 Autopilot SITL multi-vehicle simulation with Gazebo Harmonic.
        """
        lines = [
            "#!/usr/bin/env bash",
            "# Apex-HiveMind PX4 SITL Multi-Vehicle Swarm Launcher",
            "set -e",
            "",
            f"echo \"Starting {num_drones} PX4 x500 SITL Nodes in Gazebo...\"",
            "",
        ]

        for i in range(num_drones):
            lines.append(
                f"PX4_SYS_AUTOSTART=4001 PX4_GZ_MODEL_NAME=x500_{i} "
                f"./build/px4_sitl_default/bin/px4 -i {i} &"
            )

        lines.extend([
            "",
            "echo \"PX4 SITL cluster operational. Connecting MAVLink bridge on UDP 14540/14550.\"",
            "wait",
        ])
        return "\n".join(lines)
