"""
Pure Python MAVLink v1 / v2 Packet Encoder, Decoder & CRC Engine.
Zero external dependencies. Compatible with ArduPilot and PX4 SITL over UDP.
"""

from __future__ import annotations
import math
import struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


def crc16_mcrf4xx(data: bytes, initial: int = 0xFFFF) -> int:
    """CRC-16/MCRF4XX checksum matching official MAVLink specification."""
    crc = initial
    for byte in data:
        tmp = byte ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
    return crc & 0xFFFF


# MAVLink Message CRC Extra seeds
MAVLINK_CRC_EXTRA: Dict[int, int] = {
    0: 50,    # HEARTBEAT
    30: 39,   # ATTITUDE
    33: 104,  # GLOBAL_POSITION_INT
    76: 152,  # COMMAND_LONG
}

# Common MAVLink Commands
MAV_CMD_DO_FLIGHTTERMINATION = 185
MAV_CMD_DO_SET_SERVO = 183
MAV_CMD_COMPONENT_ARM_DISARM = 400
MAV_CMD_DO_MOUNT_CONTROL = 205


@dataclass
class MAVLinkMessage:
    msg_id: int
    sys_id: int
    comp_id: int
    payload: bytes


@dataclass
class GlobalPositionInt:
    time_boot_ms: int
    lat_deg: float
    lon_deg: float
    alt_msl_m: float
    relative_alt_m: float
    vx_mps: float
    vy_mps: float
    vz_mps: float
    hdg_deg: float
    sys_id: int = 1


class MAVLinkCodec:
    """
    Encodes and decodes MAVLink v1/v2 binary datagrams for SITL communications.
    """

    def __init__(self, sys_id: int = 254, comp_id: int = 1):
        self.sys_id = sys_id
        self.comp_id = comp_id
        self.seq = 0

    def decode_packet(self, data: bytes) -> Optional[MAVLinkMessage]:
        """Parses a raw UDP byte buffer into a structured MAVLink message."""
        if len(data) < 8:
            return None

        magic = data[0]

        if magic == 0xFE:
            # MAVLink v1 Frame: [FE, LEN, SEQ, SYS, COMP, MSGID, PAYLOAD..., CK_L, CK_H]
            payload_len = data[1]
            if len(data) < 6 + payload_len + 2:
                return None
            sys_id = data[3]
            comp_id = data[4]
            msg_id = data[5]
            payload = data[6 : 6 + payload_len]

            # Validate CRC
            crc_received = struct.unpack("<H", data[6 + payload_len : 8 + payload_len])[0]
            crc_extra = MAVLINK_CRC_EXTRA.get(msg_id, 0)
            crc_computed = crc16_mcrf4xx(data[1 : 6 + payload_len])
            crc_computed = crc16_mcrf4xx(bytes([crc_extra]), crc_computed)

            if crc_received != crc_computed:
                return None  # Bad checksum

            return MAVLinkMessage(msg_id=msg_id, sys_id=sys_id, comp_id=comp_id, payload=payload)

        elif magic == 0xFD:
            # MAVLink v2 Frame: [FD, LEN, INC_FLAGS, COMP_FLAGS, SEQ, SYS, COMP, MSG_ID(3B), PAYLOAD..., CK_L, CK_H]
            payload_len = data[1]
            if len(data) < 10 + payload_len + 2:
                return None
            sys_id = data[5]
            comp_id = data[6]
            msg_id = data[7] | (data[8] << 8) | (data[9] << 16)
            payload = data[10 : 10 + payload_len]

            # Validate CRC
            crc_received = struct.unpack("<H", data[10 + payload_len : 12 + payload_len])[0]
            crc_extra = MAVLINK_CRC_EXTRA.get(msg_id, 0)
            crc_computed = crc16_mcrf4xx(data[1 : 10 + payload_len])
            crc_computed = crc16_mcrf4xx(bytes([crc_extra]), crc_computed)

            if crc_received != crc_computed:
                return None

            return MAVLinkMessage(msg_id=msg_id, sys_id=sys_id, comp_id=comp_id, payload=payload)

        return None

    def decode_global_position_int(self, msg: MAVLinkMessage) -> Optional[GlobalPositionInt]:
        """Unpacks GLOBAL_POSITION_INT (Message #33)."""
        if msg.msg_id != 33 or len(msg.payload) < 28:
            return None

        # Format: <I (u32 time), i (i32 lat), i (i32 lon), i (i32 alt), i (i32 rel_alt), h (i16 vx), h (i16 vy), h (i16 vz), H (u16 hdg)
        fields = struct.unpack("<IiiiihhhH", msg.payload[:28])
        return GlobalPositionInt(
            time_boot_ms=fields[0],
            lat_deg=fields[1] / 1e7,
            lon_deg=fields[2] / 1e7,
            alt_msl_m=fields[3] / 1000.0,
            relative_alt_m=fields[4] / 1000.0,
            vx_mps=fields[5] / 100.0,  # North
            vy_mps=fields[6] / 100.0,  # East
            vz_mps=fields[7] / 100.0,  # Down
            hdg_deg=fields[8] / 100.0,
            sys_id=msg.sys_id,
        )

    def encode_command_long(
        self,
        target_sys: int,
        target_comp: int,
        command: int,
        param1: float = 0.0,
        param2: float = 0.0,
        param3: float = 0.0,
        param4: float = 0.0,
        param5: float = 0.0,
        param6: float = 0.0,
        param7: float = 0.0,
        confirmation: int = 0,
    ) -> bytes:
        """Encodes a MAVLink v1 COMMAND_LONG packet (Message #76)."""
        # Payload: 7 x float32 (28B), 1 x uint16 cmd (2B), 1 x uint8 tgt_sys, 1 x uint8 tgt_comp, 1 x uint8 conf = 33B
        payload = struct.pack(
            "<fffffffHBBB",
            param1, param2, param3, param4, param5, param6, param7,
            command, target_sys, target_comp, confirmation
        )
        msg_id = 76
        payload_len = len(payload)
        seq = self.seq & 0xFF
        self.seq = (self.seq + 1) & 0xFF

        header = struct.pack("<BBBBBB", 0xFE, payload_len, seq, self.sys_id, self.comp_id, msg_id)
        raw = header + payload

        crc_extra = MAVLINK_CRC_EXTRA[76]
        crc = crc16_mcrf4xx(raw[1:])
        crc = crc16_mcrf4xx(bytes([crc_extra]), crc)
        return raw + struct.pack("<H", crc)

    def encode_flight_termination(self, target_sys: int) -> bytes:
        """Generates emergency flight termination order for simulated kill confirmation."""
        return self.encode_command_long(
            target_sys=target_sys,
            target_comp=1,
            command=MAV_CMD_DO_FLIGHTTERMINATION,
            param1=1.0,  # 1 = Terminate flight immediately
        )
