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


if __name__ == "__main__":
    unittest.main()
