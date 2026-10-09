"""
Phase 4: Submodular Multi-Modal Weapon-Target Assignment (m-WTA) Engine.
Optimizes asymmetric intercept assignments across HPM, HEL, Missiles, C-RAM, and Interceptors.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatTarget,
    EffectorNode,
    BlueForceUnit,
    EffectorKind,
    EngagementAllocation,
)
from apex_hivemind.core.mwta_solver import MultiModalWTASolver
from apex_hivemind.phases.phase3_prioritization import PrioritizedThreat


@dataclass
class WTAAssignmentSummary:
    allocations: List[EngagementAllocation]
    total_mitigated_value: float
    total_residual_value: float
    hpm_engagements: int
    hel_engagements: int
    kinetic_engagements: int


class MultiModalWTAEngine:
    """
    Solves heterogeneous weapon-target allocation with submodular greedy heuristics
    and (1 - 1/e) optimality bounds under operational effector constraints.
    """

    def __init__(self, core_solver: Optional[MultiModalWTASolver] = None):
        self.core_solver = core_solver or MultiModalWTASolver()

    def allocate_effectors(
        self,
        effectors: List[EffectorNode],
        prioritized_threats: List[PrioritizedThreat],
        blue_force_units: List[BlueForceUnit],
    ) -> WTAAssignmentSummary:
        """
        Executes optimal weapon-target assignment across all prioritized threats.
        """
        targets = [pt.target for pt in prioritized_threats if not pt.target.neutralized]
        allocations = self.core_solver.solve_multi_modal_wta(
            effectors=effectors,
            threats=targets,
            blue_force=blue_force_units,
        )

        # Compute summary metrics
        hpm_count = sum(1 for a in allocations if a.effector_kind == EffectorKind.HIGH_POWER_MICROWAVE)
        hel_count = sum(1 for a in allocations if a.effector_kind == EffectorKind.HIGH_ENERGY_LASER)
        kinetic_count = sum(
            1 for a in allocations
            if a.effector_kind in (EffectorKind.PRECISION_MISSILE, EffectorKind.AIRBURST_GUN, EffectorKind.BLUE_INTERCEPTOR_SWARM)
        )

        # Calculate mitigated vs residual value
        target_dict = {t.target_id: t for t in targets}
        target_pk_product: Dict[str, float] = {t.target_id: 1.0 for t in targets}
        for a in allocations:
            target_pk_product[a.target_id] *= (1.0 - a.single_shot_pk)

        mitigated = sum(
            target_dict[t_id].threat_value * (1.0 - prod)
            for t_id, prod in target_pk_product.items()
            if t_id in target_dict
        )
        residual = sum(
            target_dict[t_id].threat_value * prod
            for t_id, prod in target_pk_product.items()
            if t_id in target_dict
        )

        return WTAAssignmentSummary(
            allocations=allocations,
            total_mitigated_value=round(mitigated, 2),
            total_residual_value=round(residual, 2),
            hpm_engagements=hpm_count,
            hel_engagements=hel_count,
            kinetic_engagements=kinetic_count,
        )
