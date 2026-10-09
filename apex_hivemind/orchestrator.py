"""
Master Orchestrator for Apex-HiveMind.
Unified Battle-Management & Multi-Modal C-UAS Counter-Swarm Engine across 8 Architectural Phases.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatTarget,
    EffectorNode,
    BlueForceUnit,
    EffectorKind,
    EngagementAllocation,
    HiveMindCycleReport,
)
from apex_hivemind.core.dew_scheduler import DirectedEnergyScheduler
from apex_hivemind.core.fratricide_cbf import FratricideShieldCBF
from apex_hivemind.core.mwta_solver import MultiModalWTASolver
from apex_hivemind.core.provenance_ledger import HiveMindProvenanceLedger

from apex_hivemind.phases.phase1_ingestion import MultiINTIngestionEngine, RawSensorContact
from apex_hivemind.phases.phase2_fusion import MultiSensorFusionEngine, FusedTrack
from apex_hivemind.phases.phase3_prioritization import (
    ThreatPrioritizationEngine,
    DefendedAsset,
    PrioritizedThreat,
)
from apex_hivemind.phases.phase4_mwta import MultiModalWTAEngine, WTAAssignmentSummary
from apex_hivemind.phases.phase5_dew import DirectedEnergyPhysicsEngine
from apex_hivemind.phases.phase6_fratricide import FratricideSafetyEngine, CBFSafetyCertificate
from apex_hivemind.phases.phase7_actuation_bda import ActuationAndBDAEngine, BDAResult
from apex_hivemind.phases.phase8_provenance import (
    PostQuantumProvenanceEngine,
    ForensicAuditEntry,
)


@dataclass
class EightPhaseCycleReport(HiveMindCycleReport):
    fused_tracks_count: int = 0
    prioritized_threats_count: int = 0
    hpm_allocations_count: int = 0
    hel_allocations_count: int = 0
    kinetic_allocations_count: int = 0
    merkle_root: str = ""
    pqc_signature_fingerprint: str = ""


class ApexHiveMindOrchestrator:
    """
    Master C-UAS and Swarm Battle-Management Engine across 8 Architectural Phases.
    Executes real-time sensor-to-shooter loops across kinetic and directed energy effectors
    with deterministic sub-millisecond SLAs.
    """

    def __init__(self, defended_assets: Optional[List[DefendedAsset]] = None):
        # Core engines
        self.dew_scheduler = DirectedEnergyScheduler()
        self.fratricide_shield = FratricideShieldCBF()
        self.mwta_solver = MultiModalWTASolver(
            dew_scheduler=self.dew_scheduler,
            fratricide_shield=self.fratricide_shield,
        )
        self.provenance_ledger = HiveMindProvenanceLedger()

        # 8 Architectural Phase Engines
        self.phase1_ingestion = MultiINTIngestionEngine()
        self.phase2_fusion = MultiSensorFusionEngine()
        self.phase3_prioritization = ThreatPrioritizationEngine(defended_assets=defended_assets)
        self.phase4_mwta = MultiModalWTAEngine(core_solver=self.mwta_solver)
        self.phase5_dew = DirectedEnergyPhysicsEngine(core_scheduler=self.dew_scheduler)
        self.phase6_fratricide = FratricideSafetyEngine(core_cbf=self.fratricide_shield)
        self.phase7_actuation_bda = ActuationAndBDAEngine()
        self.phase8_provenance = PostQuantumProvenanceEngine(core_ledger=self.provenance_ledger)

        # Operational state
        self.effectors: Dict[str, EffectorNode] = {}
        self.threats: Dict[str, ThreatTarget] = {}
        self.blue_force_units: Dict[str, BlueForceUnit] = {}
        self.cycle_count = 0

    def register_effector(self, effector: EffectorNode) -> None:
        self.effectors[effector.effector_id] = effector

    def register_threat(self, threat: ThreatTarget) -> None:
        self.threats[threat.target_id] = threat

    def register_blue_unit(self, blue_unit: BlueForceUnit) -> None:
        self.blue_force_units[blue_unit.unit_id] = blue_unit

    def execute_c_uas_cycle(self, dt: float = 0.05) -> HiveMindCycleReport:
        """
        Executes a real-time battle-management cycle with full backward compatibility:
        1. Kinematic state advance & target velocity propagation
        2. Multi-Modal Weapon-Target Assignment (m-WTA)
        3. Fratricide verification via Control Barrier Functions
        4. DEW thermal bloom and capacitor state updates
        5. Post-Quantum audit logging
        """
        self.cycle_count += 1
        t_start = time.perf_counter_ns()
        phase_latencies: Dict[str, float] = {}

        # 1. Advance target kinematics
        t0 = time.perf_counter_ns()
        for tgt in self.threats.values():
            if not tgt.neutralized:
                tgt.position = tgt.position + (tgt.velocity * dt)
        phase_latencies["kinematics"] = (time.perf_counter_ns() - t0) / 1000.0

        # 2. Solve m-WTA
        active_effectors = list(self.effectors.values())
        active_threats = [t for t in self.threats.values() if not t.neutralized]
        active_blue = list(self.blue_force_units.values())

        t0 = time.perf_counter_ns()
        allocations = self.mwta_solver.solve_multi_modal_wta(
            active_effectors, active_threats, active_blue
        )
        phase_latencies["mwta"] = (time.perf_counter_ns() - t0) / 1000.0

        # 3. Simulate effect on targets & update DEW physics
        t0 = time.perf_counter_ns()
        active_dwells: Dict[str, float] = {}
        active_hpm_pulses: Set[str] = set()
        neutralized_count = 0

        for alloc in allocations:
            if alloc.effector_kind == EffectorKind.HIGH_ENERGY_LASER:
                active_dwells[alloc.effector_id] = alloc.dwell_time_seconds
            elif alloc.effector_kind == EffectorKind.HIGH_POWER_MICROWAVE:
                active_hpm_pulses.add(alloc.effector_id)

            if alloc.target_id in self.threats and alloc.single_shot_pk >= 0.70:
                self.threats[alloc.target_id].neutralized = True
                neutralized_count += 1

        self.dew_scheduler.update_physics_step(
            active_effectors, active_dwells, active_hpm_pulses, dt=dt
        )
        phase_latencies["dew_physics"] = (time.perf_counter_ns() - t0) / 1000.0

        # 4. Calculate residual surviving threat value
        surviving_value = sum(
            t.threat_value for t in self.threats.values() if not t.neutralized
        )

        # 5. Measure latency & record post-quantum ledger
        t0 = time.perf_counter_ns()
        total_latency_us = (time.perf_counter_ns() - t_start) / 1000.0

        block = self.provenance_ledger.record_engagement_cycle(
            cycle_latency_us=total_latency_us,
            threats_count=len(active_threats),
            allocations=allocations,
            fratricide_interventions=0,
        )
        phase_latencies["provenance"] = (time.perf_counter_ns() - t0) / 1000.0

        return HiveMindCycleReport(
            cycle_index=self.cycle_count,
            total_cycle_latency_us=total_latency_us,
            threats_detected=len(active_threats),
            threats_neutralized=neutralized_count,
            surviving_threat_value=surviving_value,
            active_allocations=allocations,
            fratricide_violations_prevented=0,
            hash_chain_head=block.block_hash,
            phase_latencies_us=phase_latencies,
        )

    def execute_8_phase_cycle(
        self,
        raw_contacts: Optional[List[RawSensorContact]] = None,
        dt: float = 0.05,
    ) -> EightPhaseCycleReport:
        """
        Executes the comprehensive, end-to-end 8-Phase Battle Management Cycle:
          Phase 1: Ingestion & Contact Normalization
          Phase 2: Sensor Fusion & Covariance Intersection Track Association
          Phase 3: Threat Prioritization & Stackelberg Urgency Scoring
          Phase 4: Submodular Multi-Modal Weapon-Target Assignment
          Phase 5: DEW Physical Atmospheric Propagation & Dwell Computation
          Phase 6: 4D Spatio-Temporal CBF Fratricide Shield Verification
          Phase 7: Effector Actuation & Closed-Loop BDA Monitoring
          Phase 8: Post-Quantum Provenance Merkle DAG Cryptographic Signing
        """
        self.cycle_count += 1
        t_cycle_start = time.perf_counter_ns()
        phase_latencies: Dict[str, float] = {}

        # -------------------------------------------------------------
        # Phase 1: Ingestion
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        contacts = raw_contacts or []
        # If no explicit external contacts provided, synthesize from registered active threats
        if not contacts:
            for t_id, tgt in self.threats.items():
                if not tgt.neutralized:
                    contacts.append(
                        RawSensorContact(
                            contact_id=f"SYNTH-{t_id}",
                            sensor_kind="AESA_RADAR",
                            observed_position=tgt.position,
                            observed_velocity=tgt.velocity,
                            radar_cross_section_sqm=tgt.radar_cross_section_sqm,
                            signal_to_noise_ratio_db=18.0,
                        )
                    )
        phase_latencies["phase1_ingestion"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 2: Track Fusion & Covariance Intersection
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        fused_tracks = self.phase2_fusion.process_observations(contacts, dt=dt)
        phase_latencies["phase2_fusion"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 3: Prioritization & Stackelberg Urgency
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        prioritized = self.phase3_prioritization.evaluate_threats(fused_tracks)
        # Synchronize threats dictionary with prioritized targets
        for pt in prioritized:
            if pt.target.target_id not in self.threats or not self.threats[pt.target.target_id].neutralized:
                self.threats[pt.target.target_id] = pt.target
        phase_latencies["phase3_prioritization"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 4: Submodular m-WTA Allocation
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        active_effectors = list(self.effectors.values())
        active_blue = list(self.blue_force_units.values())
        wta_summary = self.phase4_mwta.allocate_effectors(
            active_effectors, prioritized, active_blue
        )
        phase_latencies["phase4_mwta"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 5: DEW Atmospheric Propagation & Kinetics
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        active_dwells: Dict[str, float] = {}
        active_hpm_pulses: Set[str] = set()

        for alloc in wta_summary.allocations:
            eff = self.effectors.get(alloc.effector_id)
            tgt = self.threats.get(alloc.target_id)
            if not eff or not tgt:
                continue

            if alloc.effector_kind == EffectorKind.HIGH_ENERGY_LASER:
                laser_prof = self.phase5_dew.calculate_laser_physics(eff, tgt)
                alloc.dwell_time_seconds = laser_prof.required_dwell_s
                active_dwells[alloc.effector_id] = laser_prof.required_dwell_s
            elif alloc.effector_kind == EffectorKind.HIGH_POWER_MICROWAVE:
                active_hpm_pulses.add(alloc.effector_id)

        self.phase5_dew.advance_physics_step(
            active_effectors, active_dwells, active_hpm_pulses, dt=dt
        )
        phase_latencies["phase5_dew"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 6: Fratricide Shield CBF Verification
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        target_positions = {t.target_id: t.position for t in self.threats.values()}
        safe_allocations, cbf_preventions = self.phase6_fratricide.filter_safe_allocations(
            allocations=wta_summary.allocations,
            effectors=self.effectors,
            targets=target_positions,
            blue_force=active_blue,
        )
        phase_latencies["phase6_fratricide"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 7: Actuation & Closed-Loop BDA
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        self.phase7_actuation_bda.dispatch_allocations(
            safe_allocations, self.effectors, self.threats
        )
        bda_results = self.phase7_actuation_bda.evaluate_bda_step(
            self.threats, self.effectors, dt=dt
        )
        neutralized_now = sum(1 for bda in bda_results if bda.confirmed_kill)
        phase_latencies["phase7_actuation_bda"] = (time.perf_counter_ns() - t0) / 1000.0

        # -------------------------------------------------------------
        # Phase 8: Post-Quantum Provenance Ledger Sealing
        # -------------------------------------------------------------
        t0 = time.perf_counter_ns()
        total_latency_us = (time.perf_counter_ns() - t_cycle_start) / 1000.0

        audit_entry = self.phase8_provenance.commit_cycle_provenance(
            cycle_index=self.cycle_count,
            cycle_latency_us=total_latency_us,
            threats_count=len(fused_tracks),
            allocations=safe_allocations,
            bda_results=bda_results,
            cbf_violations_prevented=cbf_preventions,
        )
        phase_latencies["phase8_provenance"] = (time.perf_counter_ns() - t0) / 1000.0

        surviving_val = sum(t.threat_value for t in self.threats.values() if not t.neutralized)

        return EightPhaseCycleReport(
            cycle_index=self.cycle_count,
            total_cycle_latency_us=total_latency_us,
            threats_detected=len(fused_tracks),
            threats_neutralized=neutralized_now,
            surviving_threat_value=surviving_val,
            active_allocations=safe_allocations,
            fratricide_violations_prevented=cbf_preventions,
            hash_chain_head=audit_entry.block_hash,
            phase_latencies_us=phase_latencies,
            fused_tracks_count=len(fused_tracks),
            prioritized_threats_count=len(prioritized),
            hpm_allocations_count=wta_summary.hpm_engagements,
            hel_allocations_count=wta_summary.hel_engagements,
            kinetic_allocations_count=wta_summary.kinetic_engagements,
            merkle_root=audit_entry.merkle_root,
            pqc_signature_fingerprint=audit_entry.pqc_signature_fingerprint,
        )
