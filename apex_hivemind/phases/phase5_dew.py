"""
Phase 5: Directed Energy Physics, Atmospheric Propagation & Slew Kinetics.
Models Beer-Lambert extinction, thermal blooming, spot irradiance, capacitor banks, and chiller loops.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from apex_hivemind.core.primitives import Vector3D, ThreatTarget, EffectorNode, EffectorKind
from apex_hivemind.core.dew_scheduler import DirectedEnergyScheduler


@dataclass
class LaserAtmosphericProfile:
    slant_range_m: float
    transmission_fraction: float
    spot_diameter_m: float
    peak_irradiance_w_sqm: float
    required_dwell_s: float
    thermal_blooming_factor: float


@dataclass
class HPMBeamProfile:
    slant_range_m: float
    footprint_radius_m: float
    field_strength_v_m: float
    pulse_energy_joules: float
    capacitor_draw_pct: float


class DirectedEnergyPhysicsEngine:
    """
    High-fidelity physical propagation model for High-Energy Lasers (HEL)
    and High-Power Microwave (HPM) systems in turbulent atmospheric conditions.
    """

    def __init__(
        self,
        laser_power_kw: float = 60.0,
        wavelength_um: float = 1.064,
        aperture_diameter_m: float = 0.30,
        atmospheric_extinction_coef: float = 0.00012,  # Clear maritime/desert air (1/m)
        wind_cross_velocity_mps: float = 5.0,
        core_scheduler: Optional[DirectedEnergyScheduler] = None,
    ):
        self.laser_power_kw = laser_power_kw
        self.wavelength_m = wavelength_um * 1e-6
        self.aperture_d = aperture_diameter_m
        self.gamma_extinction = atmospheric_extinction_coef
        self.wind_v = wind_cross_velocity_mps
        self.scheduler = core_scheduler or DirectedEnergyScheduler(laser_power_kw=laser_power_kw)

    def calculate_laser_physics(
        self, laser: EffectorNode, target: ThreatTarget
    ) -> LaserAtmosphericProfile:
        """
        Computes diffraction-limited spot size, Beer-Lambert attenuation,
        thermal blooming penalty, and target irradiance.
        """
        r = laser.position.distance_to(target.position)
        r = max(10.0, r)

        # 1. Beer-Lambert atmospheric transmission: exp(-gamma * R)
        transmission = math.exp(-self.gamma_extinction * r)

        # 2. Diffraction spot diameter: d_diff = 2.44 * lambda * R / D
        d_diff = 2.44 * (self.wavelength_m * r) / self.aperture_d

        # 3. Jitter contribution (assume 5 micro-radians mechanical jitter)
        d_jitter = 2.0 * (5e-6) * r
        spot_d = max(0.01, d_diff + d_jitter)

        # 4. Thermal blooming distortion parameter (approximate distortion factor N_D)
        blooming_factor = 1.0 + (0.15 * (r / 2000.0) ** 1.5)
        effective_spot_d = spot_d * math.sqrt(blooming_factor)

        # 5. Irradiance on target: P_target / Area
        p_target_w = (self.laser_power_kw * 1000.0) * transmission
        spot_area = math.pi * ((effective_spot_d / 2.0) ** 2)
        irradiance_w_sqm = p_target_w / spot_area

        # 6. Dwell time: Target thermal destruction threshold (J/m^2)
        # FPV drone plastic/composite: 1.5e7 J/m^2; Aluminum skin: 3.5e7 J/m^2
        energy_threshold = 2.5e7
        required_dwell = energy_threshold / max(1e3, irradiance_w_sqm)
        required_dwell = min(5.0, max(0.2, required_dwell))

        return LaserAtmosphericProfile(
            slant_range_m=round(r, 2),
            transmission_fraction=round(transmission, 4),
            spot_diameter_m=round(effective_spot_d, 4),
            peak_irradiance_w_sqm=round(irradiance_w_sqm, 2),
            required_dwell_s=round(required_dwell, 3),
            thermal_blooming_factor=round(blooming_factor, 3),
        )

    def calculate_hpm_physics(
        self, hpm: EffectorNode, target_range_m: float, beam_divergence_rad: float = 0.26
    ) -> HPMBeamProfile:
        """
        Computes HPM cone footprint, field strength, and capacitor bank drain.
        """
        r = max(10.0, target_range_m)
        footprint_r = r * math.tan(beam_divergence_rad / 2.0)

        # Peak power 2 Gigawatts pulsed
        p_peak_w = 2.0e9
        # Field strength E ~ sqrt(377 * P_peak / (4 * pi * R^2)) * Gain
        gain = 12.0
        field_strength = math.sqrt((377.0 * p_peak_w * gain) / (4.0 * math.pi * (r ** 2)))

        return HPMBeamProfile(
            slant_range_m=round(r, 2),
            footprint_radius_m=round(footprint_r, 2),
            field_strength_v_m=round(field_strength, 2),
            pulse_energy_joules=50000.0,  # 50 kJ per pulse
            capacitor_draw_pct=20.0,
        )

    def advance_physics_step(
        self,
        effectors: List[EffectorNode],
        active_dwells: Dict[str, float],
        active_hpm_pulses: set,
        dt: float,
    ) -> None:
        """Advances thermal saturation and capacitor recovery states."""
        self.scheduler.update_physics_step(
            effectors=effectors,
            active_dwells=active_dwells,
            active_hpm_pulses=active_hpm_pulses,
            dt=dt,
        )
