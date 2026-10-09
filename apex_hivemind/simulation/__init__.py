"""
Apex-HiveMind Simulation & SITL Gateway Package.
Connects real-time ArduPilot and PX4 swarms in Gazebo Harmonic & Classic via MAVLink.
"""

from apex_hivemind.simulation.mavlink_packet import (
    MAVLinkCodec,
    MAVLinkMessage,
    GlobalPositionInt,
    crc16_mcrf4xx,
)
from apex_hivemind.simulation.sitl_bridge import (
    SITLSwarmBridge,
    SwarmTelemetryNode,
)
from apex_hivemind.simulation.gazebo_scenario import (
    GazeboScenarioGenerator,
)

__all__ = [
    "MAVLinkCodec",
    "MAVLinkMessage",
    "GlobalPositionInt",
    "crc16_mcrf4xx",
    "SITLSwarmBridge",
    "SwarmTelemetryNode",
    "GazeboScenarioGenerator",
]
