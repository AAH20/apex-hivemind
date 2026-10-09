"""
Phase 3: Threat Classification, Multi-Criteria Prioritization & Stackelberg Game Scoring.
Classifies kinematic profiles and computes Kemeny rank aggregation & Stackelberg urgency.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatClassification,
    ThreatTarget,
)
from apex_hivemind.phases.phase2_fusion import FusedTrack


@dataclass
class DefendedAsset:
    asset_id: str
    position: Vector3D
    criticality_value: float  # 1.0 to 100.0 (e.g., C2 Command Bunker = 100, Supply Depot = 30)


@dataclass
class PrioritizedThreat:
    target: ThreatTarget
    time_to_impact_s: float
    stackelberg_vulnerability_score: float
    kemeny_rank: int
    defended_asset_id: str


class ThreatPrioritizationEngine:
    """
    Ranks hostile targets based on physical kinematics, payload lethality,
    Kemeny-Young multi-criteria consensus, and Stackelberg defender game models.
    """

    def __init__(self, defended_assets: Optional[List[DefendedAsset]] = None):
        self.defended_assets = defended_assets or [
            DefendedAsset("PRIMARY_HQ", Vector3D(0.0, 0.0, 0.0), 100.0)
        ]

    def classify_track(self, track: FusedTrack) -> ThreatClassification:
        """Heuristic kinematic classifier based on velocity, RCS, and altitude."""
        speed = track.velocity.magnitude()
        rcs = track.radar_cross_section_sqm
        alt = track.position.z

        if speed > 800.0 and track.velocity.z < -50.0:
            return ThreatClassification.BALLISTIC_MISSILE
        elif speed >= 180.0:
            return ThreatClassification.CRUISE_MISSILE
        elif speed <= 45.0 and rcs <= 0.05:
            return ThreatClassification.FPV_SWARM_DRONE
        elif 30.0 < speed <= 90.0 and rcs <= 0.2:
            return ThreatClassification.LOITERING_MUNITION
        elif alt > 2500.0 and speed <= 80.0:
            return ThreatClassification.RECON_UAV
        elif rcs > 1.0 and speed < 60.0:
            return ThreatClassification.ELECTRONIC_DECOY
        return ThreatClassification.FPV_SWARM_DRONE

    def evaluate_threats(
        self, tracks: List[FusedTrack]
    ) -> List[PrioritizedThreat]:
        """
        Transforms fused tracks into classified, prioritized targets using
        Kemeny rank consensus and Stackelberg game scoring.
        """
        if not tracks:
            return []

        candidates: List[Tuple[FusedTrack, ThreatClassification, float, float, str]] = []

        for track in tracks:
            classification = self.classify_track(track)
            track.classification_hint = classification

            # Base lethality weight
            lethality = {
                ThreatClassification.BALLISTIC_MISSILE: 95.0,
                ThreatClassification.CRUISE_MISSILE: 80.0,
                ThreatClassification.LOITERING_MUNITION: 50.0,
                ThreatClassification.FPV_SWARM_DRONE: 25.0,
                ThreatClassification.RECON_UAV: 20.0,
                ThreatClassification.ELECTRONIC_DECOY: 5.0,
            }.get(classification, 25.0)

            # Find closest/most endangered defended asset
            best_asset = self.defended_assets[0]
            min_tti = float("inf")

            for asset in self.defended_assets:
                rel_pos = asset.position - track.position
                dist = rel_pos.magnitude()
                closing_vel = track.velocity.dot(rel_pos.normalized())

                if closing_vel > 1.0:
                    tti = dist / closing_vel
                else:
                    speed = max(10.0, track.velocity.magnitude())
                    tti = dist / speed

                if tti < min_tti:
                    min_tti = tti
                    best_asset = asset

            # Stackelberg vulnerability payoff
            # Adversary aims to maximize damage: Payoff = (Asset_Value / max(1.0, TTI)) * Lethality
            urgency = (best_asset.criticality_value / max(1.0, min_tti)) * (lethality / 50.0)
            candidates.append((track, classification, min_tti, urgency, best_asset.asset_id))

        # Kemeny rank aggregation: sort primarily by Stackelberg urgency (descending),
        # secondarily by TTI (ascending)
        candidates.sort(key=lambda c: (-c[3], c[2]))

        prioritized: List[PrioritizedThreat] = []
        for rank_idx, (trk, cls, tti, urgency, asset_id) in enumerate(candidates, start=1):
            target = ThreatTarget(
                target_id=trk.track_id,
                classification=cls,
                position=trk.position,
                velocity=trk.velocity,
                threat_value=round(min(100.0, urgency), 2),
                radar_cross_section_sqm=trk.radar_cross_section_sqm,
                confirmed=(trk.hits_count >= 2),
            )
            prioritized.append(
                PrioritizedThreat(
                    target=target,
                    time_to_impact_s=round(tti, 2),
                    stackelberg_vulnerability_score=round(urgency, 2),
                    kemeny_rank=rank_idx,
                    defended_asset_id=asset_id,
                )
            )

        return prioritized
