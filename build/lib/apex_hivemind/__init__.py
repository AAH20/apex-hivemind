"""
Apex-HiveMind: Sovereign Multi-Modal Battle-Management & C-UAS Orchestration OS.
Counter-Swarm, Directed Energy Weapons & Kinetic Kill-Chain Architecture.
"""

__version__ = "1.0.0"

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatTarget,
    EffectorNode,
    BlueForceUnit,
    EffectorKind,
    ThreatClassification,
    EngagementAllocation,
    HiveMindCycleReport,
)
from apex_hivemind.orchestrator import ApexHiveMindOrchestrator

__all__ = [
    "Vector3D",
    "ThreatTarget",
    "EffectorNode",
    "BlueForceUnit",
    "EffectorKind",
    "ThreatClassification",
    "EngagementAllocation",
    "HiveMindCycleReport",
    "ApexHiveMindOrchestrator",
]
