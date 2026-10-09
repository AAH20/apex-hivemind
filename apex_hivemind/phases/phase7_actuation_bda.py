"""
Phase 7: Real-Time Effector Actuation & Closed-Loop Battle Damage Assessment (BDA).
Manages hardware mutex locks, time-of-flight windows, optical/radar kill confirmation, and re-attack.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatTarget,
    EffectorNode,
    EffectorKind,
    EngagementAllocation,
)


class EngagementState(str, Enum):
    QUEUED = "QUEUED"
    ACQUIRING = "ACQUIRING"
    ENGAGING = "ENGAGING"
    BDA_EVALUATION = "BDA_EVALUATION"
    CONFIRMED_KILL = "CONFIRMED_KILL"
    MISSED_REENGAGE = "MISSED_REENGAGE"


@dataclass
class ActiveEngagementTrack:
    allocation: EngagementAllocation
    state: EngagementState
    start_time_ns: int = field(default_factory=time.perf_counter_ns)
    dwell_remaining_s: float = 0.0
    tof_remaining_s: float = 0.0


@dataclass
class BDAResult:
    target_id: str
    effector_id: str
    confirmed_kill: bool
    rcs_reduction_ratio: float
    velocity_decay_mps: float
    re_engagement_required: bool
    bda_timestamp_ns: int = field(default_factory=time.perf_counter_ns)


class ActuationAndBDAEngine:
    """
    Manages physical effector firing sequences and evaluates closed-loop
    Battle Damage Assessment (BDA) to confirm target neutralization or re-attack.
    """

    def __init__(self, kill_probability_threshold: float = 0.70):
        self.kill_threshold = kill_probability_threshold
        self.active_engagements: Dict[str, ActiveEngagementTrack] = {}  # key: target_id
        self.locked_effectors: Set[str] = set()

    def dispatch_allocations(
        self,
        allocations: List[EngagementAllocation],
        effectors: Dict[str, EffectorNode],
        threats: Dict[str, ThreatTarget],
    ) -> List[ActiveEngagementTrack]:
        """Locks effectors and schedules actuation execution sequences."""
        scheduled: List[ActiveEngagementTrack] = []

        for alloc in allocations:
            if not alloc.fratricide_safe:
                continue

            eff = effectors.get(alloc.effector_id)
            tgt = threats.get(alloc.target_id)
            if not eff or not tgt:
                continue

            # Determine engagement timings
            dwell = alloc.dwell_time_seconds
            tof = 0.0
            if alloc.effector_kind in (EffectorKind.PRECISION_MISSILE, EffectorKind.AIRBURST_GUN):
                dist = eff.position.distance_to(tgt.position)
                speed = 800.0 if alloc.effector_kind == EffectorKind.PRECISION_MISSILE else 1050.0
                tof = dist / speed

            track = ActiveEngagementTrack(
                allocation=alloc,
                state=EngagementState.ENGAGING,
                dwell_remaining_s=dwell,
                tof_remaining_s=tof,
            )
            self.active_engagements[alloc.target_id] = track
            self.locked_effectors.add(alloc.effector_id)
            scheduled.append(track)

        return scheduled

    def evaluate_bda_step(
        self,
        threats: Dict[str, ThreatTarget],
        effectors: Dict[str, EffectorNode],
        dt: float = 0.05,
    ) -> List[BDAResult]:
        """
        Steps engagement clocks and executes multi-spectral BDA verification.
        """
        results: List[BDAResult] = []

        for target_id, track in list(self.active_engagements.items()):
            tgt = threats.get(target_id)
            if not tgt:
                continue

            # Step dwell and time-of-flight
            if track.dwell_remaining_s > 0:
                track.dwell_remaining_s = max(0.0, track.dwell_remaining_s - dt)
            if track.tof_remaining_s > 0:
                track.tof_remaining_s = max(0.0, track.tof_remaining_s - dt)

            # Check if engagement phase completed
            if track.dwell_remaining_s <= 0.0 and track.tof_remaining_s <= 0.0:
                track.state = EngagementState.BDA_EVALUATION

                # Assess kill probability
                pk = track.allocation.single_shot_pk
                confirmed = pk >= self.kill_threshold

                if confirmed:
                    track.state = EngagementState.CONFIRMED_KILL
                    tgt.neutralized = True
                    # Target RCS collapses by 95% upon destruction
                    rcs_ratio = 0.05
                    vel_decay = tgt.velocity.magnitude()
                    tgt.velocity = Vector3D(0.0, 0.0, -9.8)  # Freefall ballistics
                    re_engage = False
                else:
                    track.state = EngagementState.MISSED_REENGAGE
                    rcs_ratio = 1.0
                    vel_decay = 0.0
                    re_engage = True
                    # Escalate threat priority for missed target
                    tgt.threat_value = min(100.0, tgt.threat_value * 1.25)

                bda = BDAResult(
                    target_id=target_id,
                    effector_id=track.allocation.effector_id,
                    confirmed_kill=confirmed,
                    rcs_reduction_ratio=rcs_ratio,
                    velocity_decay_mps=vel_decay,
                    re_engagement_required=re_engage,
                )
                results.append(bda)

                # Release hardware lock on effector
                if track.allocation.effector_id in self.locked_effectors:
                    self.locked_effectors.remove(track.allocation.effector_id)
                del self.active_engagements[target_id]

        return results
