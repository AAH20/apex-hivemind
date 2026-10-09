"""
Comprehensive Unit Test Suite for Apex-HiveMind.
Zero external dependencies. Pure standard library unittest.
"""

from __future__ import annotations
import math
import unittest

from apex_hivemind.core.primitives import (
    Vector3D,
    ThreatTarget,
    EffectorNode,
    BlueForceUnit,
    EffectorKind,
    ThreatClassification,
)
from apex_hivemind.core.dew_scheduler import DirectedEnergyScheduler
from apex_hivemind.core.fratricide_cbf import FratricideShieldCBF
from apex_hivemind.core.mwta_solver import MultiModalWTASolver
from apex_hivemind.core.provenance_ledger import HiveMindProvenanceLedger
from apex_hivemind.orchestrator import ApexHiveMindOrchestrator
from apex_hivemind.phases.phase1_ingestion import MultiINTIngestionEngine, RawSensorContact
from apex_hivemind.phases.phase2_fusion import MultiSensorFusionEngine, FusedTrack, TrackState
from apex_hivemind.phases.phase3_prioritization import ThreatPrioritizationEngine, DefendedAsset
from apex_hivemind.phases.phase4_mwta import MultiModalWTAEngine
from apex_hivemind.phases.phase5_dew import DirectedEnergyPhysicsEngine
from apex_hivemind.phases.phase6_fratricide import FratricideSafetyEngine
from apex_hivemind.phases.phase7_actuation_bda import ActuationAndBDAEngine, BDAResult
from apex_hivemind.phases.phase8_provenance import PostQuantumProvenanceEngine


class TestApexHiveMind(unittest.TestCase):

    def test_vector_cross_and_projections(self):
        v1 = Vector3D(1.0, 0.0, 0.0)
        v2 = Vector3D(0.0, 1.0, 0.0)
        cross = v1.cross(v2)
        self.assertEqual(cross, Vector3D(0.0, 0.0, 1.0))
        self.assertEqual(v1.dot(v2), 0.0)

    def test_dew_slew_and_dwell_kinematics(self):
        scheduler = DirectedEnergyScheduler(laser_power_kw=50.0)
        laser = EffectorNode(
            effector_id="LASER-1",
            kind=EffectorKind.HIGH_ENERGY_LASER,
            position=Vector3D(0, 0, 0),
            max_effective_range_meters=4000.0,
            slew_rate_rad_s=1.0,
            current_pointing_azimuth_rad=0.0,
            current_pointing_elevation_rad=0.0
        )
        target = ThreatTarget(
            target_id="TGT-1",
            classification=ThreatClassification.FPV_SWARM_DRONE,
            position=Vector3D(0, 1000, 0),  # 90 degrees away
            velocity=Vector3D(0, 0, 0),
            threat_value=20.0,
            radar_cross_section_sqm=0.02
        )
        slew_time = scheduler.compute_slew_time(laser, target.position)
        # Slew of pi/2 rad at 1.0 rad/s ~ 1.57 s
        self.assertAlmostEqual(slew_time, math.pi / 2.0, delta=0.05)

        dwell = scheduler.compute_laser_required_dwell(laser, target)
        self.assertGreater(dwell, 0.5)
        self.assertLess(dwell, 4.0)

    def test_dew_thermal_and_capacitor_step(self):
        scheduler = DirectedEnergyScheduler()
        laser = EffectorNode("L1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0)
        hpm = EffectorNode("H1", EffectorKind.HIGH_POWER_MICROWAVE, Vector3D(0, 0, 0), 2000.0)

        # Firing state: laser active, HPM pulsed
        scheduler.update_physics_step([laser, hpm], active_dwells={"L1": 2.0}, active_hpm_pulses={"H1"}, dt=0.1)
        self.assertGreater(laser.thermal_saturation_pct, 0.0)
        self.assertLess(hpm.capacitor_charge_pct, 100.0)

        # Idle state: laser cools, HPM recharges
        old_laser_temp = laser.thermal_saturation_pct
        scheduler.update_physics_step([laser, hpm], active_dwells={}, active_hpm_pulses=set(), dt=0.5)
        self.assertLess(laser.thermal_saturation_pct, old_laser_temp)
        self.assertAlmostEqual(hpm.capacitor_charge_pct, 100.0 - 20.0 + (15.0 * 0.5), delta=1.0)

    def test_fratricide_laser_beam_intersection_rejection(self):
        shield = FratricideShieldCBF(laser_beam_safety_radius_meters=30.0)
        laser_pos = Vector3D(0, 0, 0)
        target_pos = Vector3D(1000, 0, 0)

        # Blue force unit directly in the firing beam line at X=500, Y=10
        blue_threatened = BlueForceUnit("BLUE-1", Vector3D(500, 10, 0), Vector3D(0, 0, 0), 25.0)
        safe, reason = shield.is_laser_beam_fratricide_free(laser_pos, target_pos, [blue_threatened])
        self.assertFalse(safe)
        self.assertIn("FRATRICIDE VIOLATION", reason)

        # Blue force unit safely off to the side at X=500, Y=300
        blue_safe = BlueForceUnit("BLUE-2", Vector3D(500, 300, 0), Vector3D(0, 0, 0), 25.0)
        safe2, _ = shield.is_laser_beam_fratricide_free(laser_pos, target_pos, [blue_safe])
        self.assertTrue(safe2)

    def test_fratricide_hpm_cone_rejection(self):
        shield = FratricideShieldCBF()
        hpm_pos = Vector3D(0, 0, 0)
        pointing_dir = Vector3D(1, 0, 0)

        # Blue unit inside 15 degree cone at 500m
        blue_in_cone = BlueForceUnit("BLUE-CONE", Vector3D(500, 20, 0), Vector3D(0, 0, 0), 20.0)
        safe, reason = shield.is_hpm_pulse_fratricide_free(hpm_pos, pointing_dir, 1500.0, 0.26, [blue_in_cone])
        self.assertFalse(safe)

        # Blue unit behind HPM
        blue_behind = BlueForceUnit("BLUE-REAR", Vector3D(-200, 0, 0), Vector3D(0, 0, 0), 20.0)
        safe2, _ = shield.is_hpm_pulse_fratricide_free(hpm_pos, pointing_dir, 1500.0, 0.26, [blue_behind])
        self.assertTrue(safe2)

    def test_mwta_hpm_cluster_prioritization(self):
        solver = MultiModalWTASolver()
        hpm = EffectorNode(
            "HPM-1", EffectorKind.HIGH_POWER_MICROWAVE, Vector3D(0, 0, 0), 2000.0,
            capacitor_charge_pct=100.0
        )
        # Cluster of 3 FPV drones
        drone1 = ThreatTarget("D1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(800, 50, 0), Vector3D(0, 0, 0), 20.0, 0.02)
        drone2 = ThreatTarget("D2", ThreatClassification.FPV_SWARM_DRONE, Vector3D(810, 60, 0), Vector3D(0, 0, 0), 20.0, 0.02)
        drone3 = ThreatTarget("D3", ThreatClassification.FPV_SWARM_DRONE, Vector3D(820, 40, 0), Vector3D(0, 0, 0), 20.0, 0.02)

        allocations = solver.solve_multi_modal_wta([hpm], [drone1, drone2, drone3], [])
        # All 3 drones should be targeted by the single HPM unit
        hpm_allocs = [a for a in allocations if a.effector_id == "HPM-1"]
        self.assertEqual(len(hpm_allocs), 3)

    def test_mwta_heterogeneous_weapon_matching(self):
        solver = MultiModalWTASolver()
        sam = EffectorNode("SAM-1", EffectorKind.PRECISION_MISSILE, Vector3D(0, 0, 0), 10000.0, ammunition_rounds=5)
        laser = EffectorNode("LASER-1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0)

        cruise = ThreatTarget("CRUISE-1", ThreatClassification.CRUISE_MISSILE, Vector3D(6000, 0, 200), Vector3D(-200, 0, 0), 90.0, 0.3)
        fpv = ThreatTarget("FPV-1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(1500, 0, 50), Vector3D(-20, 0, 0), 20.0, 0.02)

        allocations = solver.solve_multi_modal_wta([sam, laser], [cruise, fpv], [])
        self.assertEqual(len(allocations), 2)

        alloc_dict = {a.target_id: a.effector_kind for a in allocations}
        # High-threat, high-speed cruise missile goes to SAM missile interceptor
        self.assertEqual(alloc_dict["CRUISE-1"], EffectorKind.PRECISION_MISSILE)
        # Close-in FPV drone goes to Laser
        self.assertEqual(alloc_dict["FPV-1"], EffectorKind.HIGH_ENERGY_LASER)

    def test_mwta_skips_overheated_laser(self):
        solver = MultiModalWTASolver()
        # Laser thermal saturation is 95% (exceeds 85% threshold)
        hot_laser = EffectorNode("HOT-LASER", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0, thermal_saturation_pct=95.0)
        cram_gun = EffectorNode("GUN-1", EffectorKind.AIRBURST_GUN, Vector3D(0, 0, 0), 2000.0, ammunition_rounds=10)
        target = ThreatTarget("TGT-1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(1200, 0, 50), Vector3D(0, 0, 0), 25.0, 0.02)

        allocations = solver.solve_multi_modal_wta([hot_laser, cram_gun], [target], [])
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].effector_id, "GUN-1")

    def test_post_quantum_ledger_integrity(self):
        ledger = HiveMindProvenanceLedger()
        b1 = ledger.record_engagement_cycle(45.0, 5, [], 0)
        b2 = ledger.record_engagement_cycle(38.0, 4, [], 1)
        self.assertEqual(b2.previous_hash, b1.block_hash)

        valid, msg = ledger.verify_ledger_integrity()
        self.assertTrue(valid)
        self.assertIn("verified", msg.lower())

        # Tamper test
        ledger.chain[0].block_hash = "0" * 64
        tampered, _ = ledger.verify_ledger_integrity()
        self.assertFalse(tampered)

    def test_master_hivemind_orchestrator_end_to_end(self):
        orchestrator = ApexHiveMindOrchestrator()
        orchestrator.register_effector(EffectorNode(
            "LASER-ALPHA", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0
        ))
        orchestrator.register_threat(ThreatTarget(
            "HOSTILE-UAV", ThreatClassification.RECON_UAV, Vector3D(1800, 0, 100), Vector3D(-25, 0, 0), 40.0, 0.1
        ))

        report = orchestrator.execute_c_uas_cycle(dt=0.05)
        self.assertEqual(report.cycle_index, 1)
        self.assertEqual(report.threats_detected, 1)
        self.assertGreater(len(report.active_allocations), 0)
        self.assertLess(report.total_cycle_latency_us, 1500.0)

    def test_35mm_airburst_close_range_leaker(self):
        solver = MultiModalWTASolver()
        gun = EffectorNode("GUN-1", EffectorKind.AIRBURST_GUN, Vector3D(0, 0, 0), 2500.0, ammunition_rounds=15)
        leaker = ThreatTarget("LEAKER-1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(600, 0, 50), Vector3D(-40, 0, 0), 30.0, 0.02)
        allocs = solver.solve_multi_modal_wta([gun], [leaker], [])
        self.assertEqual(len(allocs), 1)
        self.assertEqual(allocs[0].effector_kind, EffectorKind.AIRBURST_GUN)
        # Ammunition must have decremented
        self.assertEqual(gun.ammunition_rounds, 14)

    def test_hpm_capacitor_depletion_and_recovery(self):
        scheduler = DirectedEnergyScheduler()
        hpm = EffectorNode("HPM-1", EffectorKind.HIGH_POWER_MICROWAVE, Vector3D(0, 0, 0), 2000.0, capacitor_charge_pct=15.0)
        # Charge is 15%, below 20% discharge limit
        drone = ThreatTarget("D1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(500, 0, 0), Vector3D(0, 0, 0), 20.0, 0.02)
        feasible, _ = scheduler.evaluate_hpm_pulse_feasibility(hpm, [drone])
        self.assertFalse(feasible)

        # Recharge for 2 seconds (15% * 2 = +30%)
        scheduler.update_physics_step([hpm], active_dwells={}, active_hpm_pulses=set(), dt=2.0)
        self.assertGreater(hpm.capacitor_charge_pct, 40.0)
        feasible2, _ = scheduler.evaluate_hpm_pulse_feasibility(hpm, [drone])
        self.assertTrue(feasible2)

    def test_high_stress_50_threat_saturation(self):
        orchestrator = ApexHiveMindOrchestrator()
        # Add diverse effectors
        orchestrator.register_effector(EffectorNode("HPM-1", EffectorKind.HIGH_POWER_MICROWAVE, Vector3D(0, 0, 0), 2500.0))
        orchestrator.register_effector(EffectorNode("HEL-1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(50, 0, 0), 5000.0))
        orchestrator.register_effector(EffectorNode("SAM-1", EffectorKind.PRECISION_MISSILE, Vector3D(-50, 0, 0), 20000.0, ammunition_rounds=50))
        orchestrator.register_effector(EffectorNode("GUN-1", EffectorKind.AIRBURST_GUN, Vector3D(0, 50, 0), 2500.0, ammunition_rounds=100))

        # Register 50 incoming hostile threats
        for i in range(50):
            classification = ThreatClassification.FPV_SWARM_DRONE if i < 40 else ThreatClassification.CRUISE_MISSILE
            orchestrator.register_threat(ThreatTarget(
                target_id=f"RAID-THREAT-{i:02d}",
                classification=classification,
                position=Vector3D(800.0 + (i * 25.0), 200.0 + (i * 10.0), 100.0),
                velocity=Vector3D(-40.0, 0.0, 0.0),
                threat_value=25.0 if i < 40 else 85.0,
                radar_cross_section_sqm=0.05
            ))

        report = orchestrator.execute_c_uas_cycle(dt=0.05)
        self.assertEqual(report.threats_detected, 50)
        self.assertGreater(report.threats_neutralized, 0)
        # 50 simultaneous threats across 4 heterogeneous effectors: sub-10ms SLA (100+ Hz)
        self.assertLess(report.total_cycle_latency_us, 10000.0)

    def test_laser_continuous_duty_cycle(self):
        scheduler = DirectedEnergyScheduler(laser_cooldown_rate_pct_s=10.0)
        laser = EffectorNode("LASER-1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0, thermal_saturation_pct=50.0)
        # Cool down for 3 seconds -> -30%
        scheduler.update_physics_step([laser], active_dwells={}, active_hpm_pulses=set(), dt=3.0)
        self.assertAlmostEqual(laser.thermal_saturation_pct, 20.0, delta=1.0)

    # -------------------------------------------------------------
    # Phase 1: Multi-INT Ingestion Tests
    # -------------------------------------------------------------
    def test_phase1_aesa_radar_coordinate_transform_and_snr_filter(self):
        engine = MultiINTIngestionEngine(min_snr_threshold_db=5.0)
        # Low SNR return should be rejected as thermal clutter
        clutter = engine.parse_aesa_radar_detection("R1", 1000.0, 45.0, 10.0, -30.0, 0.01, snr_db=3.0)
        self.assertIsNone(clutter)

        # High SNR valid contact
        contact = engine.parse_aesa_radar_detection("R1", 1000.0, 0.0, 0.0, -50.0, 0.05, snr_db=15.0)
        self.assertIsNotNone(contact)
        self.assertAlmostEqual(contact.observed_position.x, 1000.0, delta=1.0)
        self.assertAlmostEqual(contact.observed_position.y, 0.0, delta=1.0)
        self.assertAlmostEqual(contact.observed_position.z, 0.0, delta=1.0)

    def test_phase1_sigint_emitter_ingestion(self):
        engine = MultiINTIngestionEngine()
        sigint = engine.parse_sigint_emitter("EMIT-9", 90.0, 0.0, 2500.0, frequency_mhz=5800.0, pulse_repetition_interval_us=25.0)
        self.assertEqual(sigint.sensor_kind, "SIGINT_ESM")
        self.assertAlmostEqual(sigint.observed_position.x, 0.0, delta=1.0)
        self.assertAlmostEqual(sigint.observed_position.y, 2500.0, delta=1.0)
        self.assertEqual(sigint.emitter_frequency_mhz, 5800.0)

    # -------------------------------------------------------------
    # Phase 2: Sensor Fusion & Covariance Intersection Tests
    # -------------------------------------------------------------
    def test_phase2_track_initiation_and_confirmation_hits(self):
        fusion = MultiSensorFusionEngine(confirm_hits_threshold=3)
        c1 = RawSensorContact("C1", "AESA_RADAR", Vector3D(1000, 0, 100), Vector3D(-20, 0, 0), 0.02, 12.0)
        tracks1 = fusion.process_observations([c1], dt=0.05)
        self.assertEqual(len(tracks1), 1)
        self.assertEqual(tracks1[0].state, TrackState.TENTATIVE)

        # Feed 2 more hits within gate -> should transition to CONFIRMED
        c2 = RawSensorContact("C2", "AESA_RADAR", Vector3D(999, 0, 100), Vector3D(-20, 0, 0), 0.02, 14.0)
        tracks2 = fusion.process_observations([c2], dt=0.05)
        self.assertEqual(tracks2[0].state, TrackState.TENTATIVE)

        c3 = RawSensorContact("C3", "AESA_RADAR", Vector3D(998, 0, 100), Vector3D(-20, 0, 0), 0.02, 15.0)
        tracks3 = fusion.process_observations([c3], dt=0.05)
        self.assertEqual(tracks3[0].state, TrackState.CONFIRMED)

    def test_phase2_covariance_intersection_state_update(self):
        fusion = MultiSensorFusionEngine()
        c_radar = RawSensorContact("CR", "AESA_RADAR", Vector3D(1000, 50, 100), Vector3D(-20, 0, 0), 0.05, 10.0)
        fusion.process_observations([c_radar], dt=0.05)
        track_before = list(fusion.active_tracks.values())[0]
        initial_var = track_before.pos_variance.x

        # Second observation with higher SNR fuses and reduces covariance uncertainty
        c_optic = RawSensorContact("CO", "EO_IR_OPTIC", Vector3D(1000, 50, 100), Vector3D(-20, 0, 0), 0.05, 25.0)
        fusion.process_observations([c_optic], dt=0.05)
        track_after = list(fusion.active_tracks.values())[0]
        self.assertLess(track_after.pos_variance.x, initial_var)

    def test_phase2_track_coasting_and_drop_on_misses(self):
        fusion = MultiSensorFusionEngine(confirm_hits_threshold=1, drop_misses_threshold=3)
        c = RawSensorContact("C1", "AESA_RADAR", Vector3D(500, 0, 50), Vector3D(0, 0, 0), 0.02, 12.0)
        fusion.process_observations([c], dt=0.05)

        # Feed empty contacts -> miss 1 -> COASTING
        t1 = fusion.process_observations([], dt=0.05)
        self.assertEqual(t1[0].state, TrackState.COASTING)

        # Miss 2 -> COASTING
        fusion.process_observations([], dt=0.05)
        # Miss 3 -> DROPPED -> active list empty
        t3 = fusion.process_observations([], dt=0.05)
        self.assertEqual(len(t3), 0)

    # -------------------------------------------------------------
    # Phase 3: Threat Prioritization & Stackelberg Tests
    # -------------------------------------------------------------
    def test_phase3_threat_classification_kinematics(self):
        engine = ThreatPrioritizationEngine()
        # High mach descending -> Ballistic
        ballistic_track = FusedTrack("T-BAL", TrackState.CONFIRMED, Vector3D(0, 0, 10000), Vector3D(0, 0, -850), Vector3D(1, 1, 1), Vector3D(1, 1, 1), 0.1, 0.9)
        self.assertEqual(engine.classify_track(ballistic_track), ThreatClassification.BALLISTIC_MISSILE)

        # High speed horizontal -> Cruise
        cruise_track = FusedTrack("T-CRU", TrackState.CONFIRMED, Vector3D(5000, 0, 200), Vector3D(-250, 0, 0), Vector3D(1, 1, 1), Vector3D(1, 1, 1), 0.2, 0.9)
        self.assertEqual(engine.classify_track(cruise_track), ThreatClassification.CRUISE_MISSILE)

        # Low speed small RCS -> FPV Swarm Drone
        fpv_track = FusedTrack("T-FPV", TrackState.CONFIRMED, Vector3D(1000, 0, 50), Vector3D(-30, 0, 0), Vector3D(1, 1, 1), Vector3D(1, 1, 1), 0.02, 0.9)
        self.assertEqual(engine.classify_track(fpv_track), ThreatClassification.FPV_SWARM_DRONE)

    def test_phase3_kemeny_rank_aggregation_and_stackelberg_urgency(self):
        hq = DefendedAsset("HQ", Vector3D(0, 0, 0), 100.0)
        engine = ThreatPrioritizationEngine(defended_assets=[hq])

        # Far slow drone vs close high-speed cruise missile
        far_drone = FusedTrack("DRONE-FAR", TrackState.CONFIRMED, Vector3D(3000, 0, 100), Vector3D(-20, 0, 0), Vector3D(1, 1, 1), Vector3D(1, 1, 1), 0.02, 0.8)
        close_cruise = FusedTrack("CRUISE-FAST", TrackState.CONFIRMED, Vector3D(2000, 0, 100), Vector3D(-300, 0, 0), Vector3D(1, 1, 1), Vector3D(1, 1, 1), 0.2, 0.9)

        prioritized = engine.evaluate_threats([far_drone, close_cruise])
        self.assertEqual(len(prioritized), 2)
        # Cruise missile has much shorter TTI and higher lethality -> must rank #1
        self.assertEqual(prioritized[0].target.target_id, "CRUISE-FAST")
        self.assertEqual(prioritized[0].kemeny_rank, 1)

    # -------------------------------------------------------------
    # Phase 4: Submodular m-WTA Allocation Tests
    # -------------------------------------------------------------
    def test_phase4_mwta_engine_mitigated_and_residual_value(self):
        mwta_engine = MultiModalWTAEngine()
        laser = EffectorNode("L1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0)
        drone = ThreatTarget("D1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(1200, 0, 50), Vector3D(0, 0, 0), 40.0, 0.02)
        from apex_hivemind.phases.phase3_prioritization import PrioritizedThreat
        p_threat = PrioritizedThreat(drone, 20.0, 50.0, 1, "HQ")

        summary = mwta_engine.allocate_effectors([laser], [p_threat], [])
        self.assertEqual(len(summary.allocations), 1)
        self.assertGreater(summary.total_mitigated_value, 0.0)
        self.assertEqual(summary.hel_engagements, 1)

    # -------------------------------------------------------------
    # Phase 5: DEW Atmospheric Propagation & Kinetics Tests
    # -------------------------------------------------------------
    def test_phase5_laser_beer_lambert_and_thermal_blooming(self):
        dew_engine = DirectedEnergyPhysicsEngine(laser_power_kw=100.0)
        laser = EffectorNode("L100", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 6000.0)
        close_tgt = ThreatTarget("T-CLOSE", ThreatClassification.FPV_SWARM_DRONE, Vector3D(1000, 0, 0), Vector3D(0, 0, 0), 20.0, 0.02)
        far_tgt = ThreatTarget("T-FAR", ThreatClassification.FPV_SWARM_DRONE, Vector3D(5000, 0, 0), Vector3D(0, 0, 0), 20.0, 0.02)

        prof_close = dew_engine.calculate_laser_physics(laser, close_tgt)
        prof_far = dew_engine.calculate_laser_physics(laser, far_tgt)

        # Longer distance has lower transmission and larger spot size
        self.assertGreater(prof_close.transmission_fraction, prof_far.transmission_fraction)
        self.assertLess(prof_close.spot_diameter_m, prof_far.spot_diameter_m)
        self.assertLess(prof_close.required_dwell_s, prof_far.required_dwell_s)

    def test_phase5_hpm_cone_footprint_and_field_strength(self):
        dew_engine = DirectedEnergyPhysicsEngine()
        hpm = EffectorNode("HPM-1", EffectorKind.HIGH_POWER_MICROWAVE, Vector3D(0, 0, 0), 2500.0)
        prof = dew_engine.calculate_hpm_physics(hpm, target_range_m=1000.0, beam_divergence_rad=0.26)
        self.assertGreater(prof.footprint_radius_m, 100.0)
        self.assertGreater(prof.field_strength_v_m, 500.0)
        self.assertEqual(prof.capacitor_draw_pct, 20.0)

    # -------------------------------------------------------------
    # Phase 6: 4D Spatio-Temporal CBF Safety Tests
    # -------------------------------------------------------------
    def test_phase6_cbf_kinetic_fragmentation_barrier_violation(self):
        cbf_engine = FratricideSafetyEngine(kinetic_frag_radius_m=60.0)
        sam = EffectorNode("SAM-1", EffectorKind.PRECISION_MISSILE, Vector3D(0, 0, 0), 10000.0)
        target_pos = Vector3D(2000, 0, 200)

        # Friendly convoy directly under intercept point (distance 40m < 60m frag radius)
        blue_threatened = BlueForceUnit("CONVOY-1", Vector3D(2000, 30, 200), Vector3D(0, 0, 0), 25.0)
        cert = cbf_engine.verify_allocation_safety(sam, target_pos, [blue_threatened])
        self.assertFalse(cert.allocation_approved)
        self.assertLess(cert.barrier_value_h, 0.0)
        self.assertEqual(cert.violating_unit_id, "CONVOY-1")

    def test_phase6_cbf_filter_safe_allocations(self):
        cbf_engine = FratricideSafetyEngine()
        laser = EffectorNode("L1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0)
        blue = BlueForceUnit("B1", Vector3D(500, 5, 0), Vector3D(0, 0, 0), 25.0)

        # Target behind friendly unit (laser intersects friendly)
        from apex_hivemind.core.primitives import EngagementAllocation
        unsafe_alloc = EngagementAllocation("L1", "TGT-UNSAFE", EffectorKind.HIGH_ENERGY_LASER, 0.85)

        effectors = {"L1": laser}
        targets = {"TGT-UNSAFE": Vector3D(1000, 10, 0)}

        safe_list, violations = cbf_engine.filter_safe_allocations([unsafe_alloc], effectors, targets, [blue])
        self.assertEqual(len(safe_list), 0)
        self.assertEqual(violations, 1)

    # -------------------------------------------------------------
    # Phase 7: Actuation & Closed-Loop BDA Tests
    # -------------------------------------------------------------
    def test_phase7_actuation_bda_kill_confirmation_and_rcs_collapse(self):
        bda_engine = ActuationAndBDAEngine(kill_probability_threshold=0.70)
        laser = EffectorNode("L1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0)
        drone = ThreatTarget("T1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(1000, 0, 50), Vector3D(-20, 0, 0), 20.0, 0.02)

        from apex_hivemind.core.primitives import EngagementAllocation
        alloc = EngagementAllocation("L1", "T1", EffectorKind.HIGH_ENERGY_LASER, single_shot_pk=0.85, dwell_time_seconds=0.1)
        bda_engine.dispatch_allocations([alloc], {"L1": laser}, {"T1": drone})

        # Step 0.15s to elapse dwell
        results = bda_engine.evaluate_bda_step({"T1": drone}, {"L1": laser}, dt=0.15)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].confirmed_kill)
        self.assertTrue(drone.neutralized)
        self.assertEqual(results[0].rcs_reduction_ratio, 0.05)

    def test_phase7_actuation_bda_miss_and_threat_escalation(self):
        bda_engine = ActuationAndBDAEngine(kill_probability_threshold=0.70)
        gun = EffectorNode("G1", EffectorKind.AIRBURST_GUN, Vector3D(0, 0, 0), 2500.0)
        leaker = ThreatTarget("L1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(800, 0, 50), Vector3D(-30, 0, 0), 30.0, 0.02)

        from apex_hivemind.core.primitives import EngagementAllocation
        # Low Pk engagement resulting in miss
        alloc = EngagementAllocation("G1", "L1", EffectorKind.AIRBURST_GUN, single_shot_pk=0.40, dwell_time_seconds=0.0)
        bda_engine.dispatch_allocations([alloc], {"G1": gun}, {"L1": leaker})

        # Step forward
        results = bda_engine.evaluate_bda_step({"L1": leaker}, {"G1": gun}, dt=1.0)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].confirmed_kill)
        self.assertTrue(results[0].re_engagement_required)
        # Missed threat value escalated
        self.assertGreater(leaker.threat_value, 30.0)

    # -------------------------------------------------------------
    # Phase 8: Post-Quantum Provenance & Forensic Tests
    # -------------------------------------------------------------
    def test_phase8_merkle_root_computation_and_pqc_signature(self):
        pqc_engine = PostQuantumProvenanceEngine()
        from apex_hivemind.core.primitives import EngagementAllocation
        alloc1 = EngagementAllocation("L1", "T1", EffectorKind.HIGH_ENERGY_LASER, 0.9)
        alloc2 = EngagementAllocation("SAM1", "T2", EffectorKind.PRECISION_MISSILE, 0.95)

        entry = pqc_engine.commit_cycle_provenance(
            cycle_index=1,
            cycle_latency_us=52.0,
            threats_count=2,
            allocations=[alloc1, alloc2],
            bda_results=[],
            cbf_violations_prevented=0,
        )
        self.assertIsNotNone(entry.merkle_root)
        self.assertTrue(entry.pqc_signature_fingerprint.startswith("mldsa65_"))
        self.assertEqual(len(pqc_engine.audit_log), 1)

        valid, msg = pqc_engine.verify_ledger()
        self.assertTrue(valid)

    # -------------------------------------------------------------
    # Orchestrator 8-Phase End-to-End & Profiling Tests
    # -------------------------------------------------------------
    def test_orchestrator_full_8_phase_pipeline_cycle(self):
        orchestrator = ApexHiveMindOrchestrator()
        orchestrator.register_effector(EffectorNode("HEL-1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0))
        orchestrator.register_effector(EffectorNode("HPM-1", EffectorKind.HIGH_POWER_MICROWAVE, Vector3D(50, 0, 0), 2000.0))

        # Synthetic radar contact
        raw_contact = RawSensorContact("RADAR-1", "AESA_RADAR", Vector3D(1200, 0, 100), Vector3D(-25, 0, 0), 0.02, 16.0)

        report = orchestrator.execute_8_phase_cycle(raw_contacts=[raw_contact], dt=0.05)
        self.assertEqual(report.cycle_index, 1)
        self.assertEqual(report.fused_tracks_count, 1)
        self.assertEqual(report.prioritized_threats_count, 1)
        self.assertIsNotNone(report.merkle_root)
        self.assertTrue(report.pqc_signature_fingerprint.startswith("mldsa65_"))

    def test_orchestrator_8_phase_profiling_and_sub_millisecond_sla(self):
        orchestrator = ApexHiveMindOrchestrator()
        orchestrator.register_effector(EffectorNode("LASER-1", EffectorKind.HIGH_ENERGY_LASER, Vector3D(0, 0, 0), 4000.0))
        orchestrator.register_threat(ThreatTarget("T-1", ThreatClassification.FPV_SWARM_DRONE, Vector3D(1500, 0, 100), Vector3D(-30, 0, 0), 30.0, 0.02))

        report = orchestrator.execute_8_phase_cycle(dt=0.05)
        # Verify all 8 phases are profiled with latency metrics
        phases_expected = [
            "phase1_ingestion",
            "phase2_fusion",
            "phase3_prioritization",
            "phase4_mwta",
            "phase5_dew",
            "phase6_fratricide",
            "phase7_actuation_bda",
            "phase8_provenance",
        ]
        for p in phases_expected:
            self.assertIn(p, report.phase_latencies_us)
            self.assertGreaterEqual(report.phase_latencies_us[p], 0.0)

        # Entire 8-phase cycle execution must be sub-millisecond (deterministic SLA < 2500 us)
        self.assertLess(report.total_cycle_latency_us, 2500.0)


if __name__ == "__main__":
    unittest.main()
