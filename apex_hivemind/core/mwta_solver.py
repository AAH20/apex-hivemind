"""
Multi-Modal Weapon-Target Assignment (m-WTA) Solver for Apex-HiveMind.
Solves NP-Hard generalized assignment across heterogeneous effectors:
- High-Power Microwave (HPM) for wide-area dense swarm clusters
- High-Energy Lasers (HEL) for medium-range thermal burns
- Kinetic Interceptor Missiles for high-mach ballistic/cruise threats
- 35mm Airburst Guns for close-in saturation leakers
- Blue Interceptor Swarms for loitering swarm dogfights
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Set, Tuple

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatTarget,
    EffectorNode,
    BlueForceUnit,
    EffectorKind,
    ThreatClassification,
    EngagementAllocation,
)
from apex_hivemind.core.dew_scheduler import DirectedEnergyScheduler
from apex_hivemind.core.fratricide_cbf import FratricideShieldCBF


class MultiModalWTASolver:
    """
    Submodular knapsack m-WTA engine optimizing global surviving threat value.
    Dispatches heterogeneous effectors under strict thermal, capacitor,
    ammo, and friendly-fire safety invariants.
    """

    def __init__(
        self,
        dew_scheduler: Optional[DirectedEnergyScheduler] = None,
        fratricide_shield: Optional[FratricideShieldCBF] = None
    ):
        self.dew = dew_scheduler or DirectedEnergyScheduler()
        self.shield = fratricide_shield or FratricideShieldCBF()

    def estimate_single_shot_pk(
        self,
        effector: EffectorNode,
        target: ThreatTarget
    ) -> float:
        """
        Estimates conditional probability of kill P_k(i, j) based on kinematics and classification.
        """
        dist = effector.position.distance_to(target.position)
        if dist > effector.max_effective_range_meters or dist < effector.min_effective_range_meters:
            return 0.0

        range_factor = 1.0 - (dist / effector.max_effective_range_meters) * 0.4

        if effector.kind == EffectorKind.HIGH_POWER_MICROWAVE:
            # HPM is lethal against micro/small drone electronics, ineffective against armored ballistic missiles
            if target.classification in (ThreatClassification.FPV_SWARM_DRONE, ThreatClassification.RECON_UAV):
                return 0.92 * range_factor
            return 0.15

        elif effector.kind == EffectorKind.HIGH_ENERGY_LASER:
            dwell = self.dew.compute_laser_required_dwell(effector, target)
            if dwell > 4.5:
                return 0.40  # Marginal burn at long range
            return 0.88 * range_factor

        elif effector.kind == EffectorKind.PRECISION_MISSILE:
            # High Pk against high-speed cruise/ballistic targets; penalized for micro-drones
            if target.classification in (ThreatClassification.CRUISE_MISSILE, ThreatClassification.BALLISTIC_MISSILE):
                return 0.95 * range_factor
            return 0.25 * range_factor  # Inefficient to deploy heavy SAM on micro drone

        elif effector.kind == EffectorKind.AIRBURST_GUN:
            # Lethal at close range (<1500m)
            if dist <= 1500.0:
                return 0.85
            return 0.30

        elif effector.kind == EffectorKind.BLUE_INTERCEPTOR_SWARM:
            return 0.80 * range_factor

        return 0.50

    def solve_multi_modal_wta(
        self,
        effectors: List[EffectorNode],
        threats: List[ThreatTarget],
        blue_force: List[BlueForceUnit]
    ) -> List[EngagementAllocation]:
        """
        Executes optimal heterogeneous assignment.
        Returns ordered list of authorized engagement allocations.
        """
        active_threats = [t for t in threats if not t.neutralized and t.confirmed]
        if not active_threats or not effectors:
            return []

        allocations: List[EngagementAllocation] = []
        assigned_threat_ids: Set[str] = set()

        # -------------------------------------------------------------
        # Phase 1: High-Power Microwave (HPM) Area Cluster Strike
        # -------------------------------------------------------------
        hpm_units = [
            e for e in effectors
            if e.kind == EffectorKind.HIGH_POWER_MICROWAVE and e.is_operational and e.capacitor_charge_pct >= 20.0
        ]
        drone_swarm_threats = [
            t for t in active_threats
            if t.classification in (ThreatClassification.FPV_SWARM_DRONE, ThreatClassification.LOITERING_MUNITION)
        ]

        for hpm in hpm_units:
            # Find cluster center
            feasible, caught_ids = self.dew.evaluate_hpm_pulse_feasibility(
                hpm, drone_swarm_threats
            )
            if feasible and len(caught_ids) >= 2:
                # Target centroid of cluster
                cluster_targets = [t for t in drone_swarm_threats if t.target_id in caught_ids]
                cx = sum(t.position.x for t in cluster_targets) / len(cluster_targets)
                cy = sum(t.position.y for t in cluster_targets) / len(cluster_targets)
                cz = sum(t.position.z for t in cluster_targets) / len(cluster_targets)
                target_centroid = Vector3D(cx, cy, cz)

                # Fratricide check
                safe, _ = self.shield.validate_effector_firing_safety(hpm, target_centroid, blue_force)
                if safe:
                    for tid in caught_ids:
                        allocations.append(EngagementAllocation(
                            effector_id=hpm.effector_id,
                            target_id=tid,
                            effector_kind=EffectorKind.HIGH_POWER_MICROWAVE,
                            single_shot_pk=0.90,
                            fratricide_safe=True,
                            intercept_point=target_centroid
                        ))
                        assigned_threat_ids.add(tid)
                    hpm.capacitor_charge_pct -= 20.0

        # Remaining unassigned threats sorted by threat value
        residual_threats = [t for t in active_threats if t.target_id not in assigned_threat_ids]
        residual_threats.sort(key=lambda t: t.threat_value, reverse=True)

        # -------------------------------------------------------------
        # Phase 2: High-Energy Laser (HEL) & Kinetic Missiles
        # -------------------------------------------------------------
        for target in residual_threats:
            best_effector: Optional[EffectorNode] = None
            highest_marginal_gain = 0.0
            best_dwell = 0.0

            for eff in effectors:
                if not eff.is_operational:
                    continue

                # State resource checks
                if eff.kind == EffectorKind.HIGH_ENERGY_LASER and eff.thermal_saturation_pct > 85.0:
                    continue
                if eff.kind in (EffectorKind.PRECISION_MISSILE, EffectorKind.AIRBURST_GUN) and eff.ammunition_rounds <= 0:
                    continue

                pk = self.estimate_single_shot_pk(eff, target)
                if pk < 0.20:
                    continue

                # Fratricide safety gate
                safe, _ = self.shield.validate_effector_firing_safety(eff, target.position, blue_force)
                if not safe:
                    continue

                marginal_gain = target.threat_value * pk
                dwell_time = 0.0

                if eff.kind == EffectorKind.HIGH_ENERGY_LASER:
                    dwell_time = self.dew.compute_laser_required_dwell(eff, target)
                    # Penalize lasers with long dwell times to avoid turret lock
                    marginal_gain = marginal_gain / max(dwell_time, 1.0)

                if marginal_gain > highest_marginal_gain:
                    highest_marginal_gain = marginal_gain
                    best_effector = eff
                    best_dwell = dwell_time

            if best_effector is not None:
                allocations.append(EngagementAllocation(
                    effector_id=best_effector.effector_id,
                    target_id=target.target_id,
                    effector_kind=best_effector.kind,
                    single_shot_pk=self.estimate_single_shot_pk(best_effector, target),
                    dwell_time_seconds=best_dwell,
                    rounds_fired=1,
                    fratricide_safe=True,
                    intercept_point=target.position
                ))
                assigned_threat_ids.add(target.target_id)

                # Decrement effector resource
                if best_effector.kind in (EffectorKind.PRECISION_MISSILE, EffectorKind.AIRBURST_GUN):
                    best_effector.ammunition_rounds -= 1
                elif best_effector.kind == EffectorKind.HIGH_ENERGY_LASER:
                    best_effector.thermal_saturation_pct += (best_dwell * 8.0)

        return allocations
