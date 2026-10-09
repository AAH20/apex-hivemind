"""
Phase 2: Multi-Sensor Track Fusion, Clutter Rejection & Covariance Intersection.
Correlates AESA, EO/IR, and SIGINT contacts into persistent 3D kinematic tracks.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from apex_hivemind.core.primitives import Vector3D, ThreatClassification
from apex_hivemind.phases.phase1_ingestion import RawSensorContact


class TrackState(str, Enum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    COASTING = "COASTING"
    DROPPED = "DROPPED"


@dataclass
class FusedTrack:
    track_id: str
    state: TrackState
    position: Vector3D
    velocity: Vector3D
    pos_variance: Vector3D  # Diagonal covariance (sigma_x^2, sigma_y^2, sigma_z^2)
    vel_variance: Vector3D
    radar_cross_section_sqm: float
    confidence_score: float  # 0.0 to 1.0
    classification_hint: Optional[ThreatClassification] = None
    hits_count: int = 1
    misses_count: int = 0
    last_update_ns: int = field(default_factory=time.perf_counter_ns)


class MultiSensorFusionEngine:
    """
    Real-time multi-target tracking engine utilizing gating, track-to-observation
    association, and Covariance Intersection for multi-sensor state fusion.
    """

    def __init__(
        self,
        gate_threshold_m: float = 75.0,
        confirm_hits_threshold: int = 3,
        drop_misses_threshold: int = 4,
    ):
        self.gate_threshold = gate_threshold_m
        self.confirm_hits_threshold = confirm_hits_threshold
        self.drop_misses_threshold = drop_misses_threshold
        self.active_tracks: Dict[str, FusedTrack] = {}
        self._next_track_num = 1

    def predict_tracks(self, dt: float) -> None:
        """Linear kinematic extrapolation of all active tracks."""
        for track in self.active_tracks.values():
            if track.state != TrackState.DROPPED:
                track.position = track.position + (track.velocity * dt)
                # Grow position uncertainty during coasting
                growth = 0.5 * dt
                track.pos_variance = Vector3D(
                    track.pos_variance.x + growth,
                    track.pos_variance.y + growth,
                    track.pos_variance.z + growth,
                )

    def process_observations(
        self, contacts: List[RawSensorContact], dt: float = 0.05
    ) -> List[FusedTrack]:
        """
        Gating, association, and Covariance Intersection update step.
        Returns the list of currently CONFIRMED or active tracks.
        """
        self.predict_tracks(dt)
        matched_tracks = set()

        for contact in contacts:
            best_track_id: Optional[str] = None
            min_dist = float("inf")

            # 1. Gating search
            for t_id, track in self.active_tracks.items():
                if track.state == TrackState.DROPPED:
                    continue
                d = track.position.distance_to(contact.observed_position)
                if d <= self.gate_threshold and d < min_dist:
                    min_dist = d
                    best_track_id = t_id

            if best_track_id is not None:
                # 2. Covariance Intersection Update with matched track
                self._update_track_with_contact(
                    self.active_tracks[best_track_id], contact, dt
                )
                matched_tracks.add(best_track_id)
            else:
                # 3. Initialize new tentative track
                new_track_id = self._initiate_track(contact)
                matched_tracks.add(new_track_id)

        # 4. Coasting and drop logic for unmatched tracks
        for t_id, track in list(self.active_tracks.items()):
            if track.state == TrackState.DROPPED:
                continue
            if t_id not in matched_tracks:
                track.misses_count += 1
                if track.misses_count >= self.drop_misses_threshold:
                    track.state = TrackState.DROPPED
                else:
                    track.state = TrackState.COASTING

        # Filter out dropped tracks
        return [
            t
            for t in self.active_tracks.values()
            if t.state in (TrackState.CONFIRMED, TrackState.TENTATIVE, TrackState.COASTING)
        ]

    def _update_track_with_contact(
        self, track: FusedTrack, contact: RawSensorContact, dt: float
    ) -> None:
        """Applies diagonal Covariance Intersection between prior track and observation."""
        track.hits_count += 1
        track.misses_count = 0
        if track.hits_count >= self.confirm_hits_threshold:
            track.state = TrackState.CONFIRMED

        # Sensor observation variance based on SNR
        noise_scale = max(0.1, 10.0 / max(1.0, contact.signal_to_noise_ratio_db))
        obs_var = Vector3D(noise_scale * 5.0, noise_scale * 5.0, noise_scale * 8.0)

        # Covariance intersection weight omega = 0.5 (equal balance)
        # 1/P_fused = omega/P_track + (1-omega)/P_obs
        w = 0.5
        inv_fused_x = (w / track.pos_variance.x) + ((1.0 - w) / obs_var.x)
        inv_fused_y = (w / track.pos_variance.y) + ((1.0 - w) / obs_var.y)
        inv_fused_z = (w / track.pos_variance.z) + ((1.0 - w) / obs_var.z)

        p_fused = Vector3D(1.0 / inv_fused_x, 1.0 / inv_fused_y, 1.0 / inv_fused_z)

        fused_pos = Vector3D(
            p_fused.x
            * ((w * track.position.x / track.pos_variance.x) + ((1.0 - w) * contact.observed_position.x / obs_var.x)),
            p_fused.y
            * ((w * track.position.y / track.pos_variance.y) + ((1.0 - w) * contact.observed_position.y / obs_var.y)),
            p_fused.z
            * ((w * track.position.z / track.pos_variance.z) + ((1.0 - w) * contact.observed_position.z / obs_var.z)),
        )

        track.position = fused_pos
        track.pos_variance = p_fused

        # Velocity update
        if contact.observed_velocity.magnitude() > 0.1:
            track.velocity = (track.velocity * 0.7) + (contact.observed_velocity * 0.3)

        # RCS update (exponential moving average)
        if contact.radar_cross_section_sqm > 0:
            track.radar_cross_section_sqm = (
                track.radar_cross_section_sqm * 0.8
            ) + (contact.radar_cross_section_sqm * 0.2)

        # Confidence update
        track.confidence_score = min(
            1.0, 0.4 + (0.1 * track.hits_count) + (0.01 * contact.signal_to_noise_ratio_db)
        )
        track.last_update_ns = time.perf_counter_ns()

    def _initiate_track(self, contact: RawSensorContact) -> str:
        """Instantiates a new tentative track from an unassociated contact."""
        t_id = f"TRK-{self._next_track_num:04d}"
        self._next_track_num += 1

        pos_var = Vector3D(15.0, 15.0, 25.0)
        vel_var = Vector3D(5.0, 5.0, 5.0)

        initial_state = TrackState.CONFIRMED if self.confirm_hits_threshold <= 1 else TrackState.TENTATIVE
        self.active_tracks[t_id] = FusedTrack(
            track_id=t_id,
            state=initial_state,
            position=contact.observed_position,
            velocity=contact.observed_velocity,
            pos_variance=pos_var,
            vel_variance=vel_var,
            radar_cross_section_sqm=contact.radar_cross_section_sqm,
            confidence_score=0.4,
            hits_count=1,
            misses_count=0,
        )
        return t_id
