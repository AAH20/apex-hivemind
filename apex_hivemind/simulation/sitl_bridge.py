"""
Real-Time SITL Bridge for ArduPilot & PX4 Swarms in Gazebo.
Translates MAVLink telemetry to Phase 1 RawSensorContacts and executes closed-loop kill feedback.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from apex_hivemind.core.primitives import Vector3D, ThreatClassification
from apex_hivemind.phases.phase1_ingestion import RawSensorContact
from apex_hivemind.simulation.mavlink_packet import (
    GlobalPositionInt,
    MAVLinkCodec,
    MAVLinkMessage,
)


@dataclass
class SwarmTelemetryNode:
    sys_id: int
    lat_deg: float
    lon_deg: float
    alt_msl_m: float
    relative_alt_m: float
    position_cartesian: Vector3D
    velocity_cartesian: Vector3D
    heading_deg: float
    last_heard_ns: int = field(default_factory=time.perf_counter_ns)
    remote_addr: Optional[Tuple[str, int]] = None
    terminated: bool = False


class SITLSwarmBridge:
    """
    Multiplexes multi-vehicle MAVLink telemetry streams from ArduPilot SITL / PX4 SITL
    running within a Gazebo physics world into canonical Apex-HiveMind coordinates.
    """

    def __init__(
        self,
        base_origin_lat: float = 37.7749,   # Default test site (e.g. San Francisco or White Sands)
        base_origin_lon: float = -122.4194,
        base_origin_alt_m: float = 100.0,
        radar_rcs_estimate_sqm: float = 0.02,
    ):
        self.origin_lat = base_origin_lat
        self.origin_lon = base_origin_lon
        self.origin_alt = base_origin_alt_m
        self.rcs_estimate = radar_rcs_estimate_sqm

        self.codec = MAVLinkCodec()
        self.active_vehicles: Dict[int, SwarmTelemetryNode] = {}
        self.udp_sock: Optional[socket.socket] = None

    def wgs84_to_cartesian_enu(
        self, lat: float, lon: float, alt_rel: float
    ) -> Vector3D:
        """
        Converts WGS84 Geodetic coordinates to local East-North-Up (ENU) Cartesian frame.
        """
        r_earth = 6378137.0  # WGS84 equatorial radius in meters
        d_lat_rad = math.radians(lat - self.origin_lat)
        d_lon_rad = math.radians(lon - self.origin_lon)
        lat_mid_rad = math.radians((lat + self.origin_lat) / 2.0)

        # East (X), North (Y), Up (Z)
        x_east = d_lon_rad * r_earth * math.cos(lat_mid_rad)
        y_north = d_lat_rad * r_earth
        z_up = alt_rel
        return Vector3D(x_east, y_north, z_up)

    def process_mavlink_datagram(
        self, data: bytes, remote_addr: Optional[Tuple[str, int]] = None
    ) -> Optional[RawSensorContact]:
        """
        Decodes incoming MAVLink datagram and maps to RawSensorContact.
        """
        msg = self.codec.decode_packet(data)
        if not msg:
            return None

        # Process GLOBAL_POSITION_INT (msg #33)
        if msg.msg_id == 33:
            pos = self.codec.decode_global_position_int(msg)
            if not pos:
                return None

            cart_pos = self.wgs84_to_cartesian_enu(pos.lat_deg, pos.lon_deg, pos.relative_alt_m)
            # MAVLink reports: vx = North, vy = East, vz = Down.
            # Local ENU frame: X = East (vy), Y = North (vx), Z = Up (-vz).
            cart_vel = Vector3D(pos.vy_mps, pos.vx_mps, -pos.vz_mps)

            node = SwarmTelemetryNode(
                sys_id=pos.sys_id,
                lat_deg=pos.lat_deg,
                lon_deg=pos.lon_deg,
                alt_msl_m=pos.alt_msl_m,
                relative_alt_m=pos.relative_alt_m,
                position_cartesian=cart_pos,
                velocity_cartesian=cart_vel,
                heading_deg=pos.hdg_deg,
                remote_addr=remote_addr,
            )
            self.active_vehicles[pos.sys_id] = node

            # Formulate Phase 1 Contact
            return RawSensorContact(
                contact_id=f"MAVLINK-UAV-{pos.sys_id:03d}",
                sensor_kind="AESA_RADAR",
                observed_position=cart_pos,
                observed_velocity=cart_vel,
                radar_cross_section_sqm=self.rcs_estimate,
                signal_to_noise_ratio_db=22.0,
            )

        return None

    def execute_closed_loop_kill(
        self, sys_id: int, sock: Optional[socket.socket] = None
    ) -> bool:
        """
        Sends flight termination MAVLink packet back to the specified vehicle
        causing Gazebo/ArduPilot/PX4 to immediately cut motors and crash.
        """
        node = self.active_vehicles.get(sys_id)
        if not node:
            return False

        term_packet = self.codec.encode_flight_termination(target_sys=sys_id)
        node.terminated = True

        # Send over UDP if socket and remote address available
        active_sock = sock or self.udp_sock
        if active_sock and node.remote_addr:
            try:
                active_sock.sendto(term_packet, node.remote_addr)
                return True
            except OSError:
                return False

        return True

    def inject_synthetic_swarm_frame(
        self,
        count: int = 5,
        target_center_dist_m: float = 1200.0,
        closing_speed_mps: float = 35.0,
    ) -> List[RawSensorContact]:
        """
        Generates realistic synthetic MAVLink SITL frames for zero-dependency testing.
        """
        contacts: List[RawSensorContact] = []
        r_earth = 6378137.0

        for i in range(1, count + 1):
            # Drone positioned along eastern azimuth approaching base
            x = target_center_dist_m + (i * 25.0)
            y = (i - (count / 2.0)) * 30.0
            z = 60.0 + (i * 5.0)

            # Convert back to lat/lon for packet synthesis
            lat = self.origin_lat + math.degrees(y / r_earth)
            lon = self.origin_lon + math.degrees(x / (r_earth * math.cos(math.radians(self.origin_lat))))

            pos_int = GlobalPositionInt(
                time_boot_ms=int(time.time() * 1000) % 10000000,
                lat_deg=lat,
                lon_deg=lon,
                alt_msl_m=self.origin_alt + z,
                relative_alt_m=z,
                vx_mps=0.0,                 # North
                vy_mps=-closing_speed_mps,  # East (closing towards base)
                vz_mps=0.0,
                hdg_deg=270.0,              # Heading West
                sys_id=i,
            )

            # Pack MAVLink v1 GLOBAL_POSITION_INT payload
            payload = struct.pack(
                "<IiiiihhhH",
                pos_int.time_boot_ms,
                int(pos_int.lat_deg * 1e7),
                int(pos_int.lon_deg * 1e7),
                int(pos_int.alt_msl_m * 1000),
                int(pos_int.relative_alt_m * 1000),
                int(pos_int.vx_mps * 100),
                int(pos_int.vy_mps * 100),
                int(pos_int.vz_mps * 100),
                int(pos_int.hdg_deg * 100),
            )
            raw_msg = self.codec.encode_command_long(
                target_sys=i, target_comp=1, command=0
            )  # Placeholder to increment seq
            # Encode real msg 33
            seq = i & 0xFF
            header = struct.pack("<BBBBBB", 0xFE, len(payload), seq, i, 1, 33)
            raw = header + payload
            from apex_hivemind.simulation.mavlink_packet import crc16_mcrf4xx, MAVLINK_CRC_EXTRA
            crc = crc16_mcrf4xx(raw[1:])
            crc = crc16_mcrf4xx(bytes([MAVLINK_CRC_EXTRA[33]]), crc)
            packet = raw + struct.pack("<H", crc)

            contact = self.process_mavlink_datagram(packet, remote_addr=("127.0.0.1", 14550 + i))
            if contact:
                contacts.append(contact)

        return contacts
