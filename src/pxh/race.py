"""Autonomous track racing with learning.

Two-phase system: map the track during practice, race with per-lap learning.
See docs/superpowers/specs/2026-03-19-px-race-design.md for full spec.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class PDController:
    """Proportional-Derivative controller with output clamping."""

    def __init__(self, kp: float, kd: float, output_min: float = -30.0, output_max: float = 30.0):
        self.kp = kp
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self._prev_error: float | None = None

    def update(self, error: float, dt: float) -> float:
        p = self.kp * error
        if self._prev_error is not None and dt > 0:
            d = self.kd * (error - self._prev_error) / dt
        else:
            d = 0.0
        self._prev_error = error
        return clamp(p + d, self.output_min, self.output_max)

    def reset(self) -> None:
        self._prev_error = None


def normalize_grayscale(readings: list[float], track_ref: list[float], barrier_ref: list[float]) -> list[float]:
    """Normalize grayscale readings to 0.0 (track) - 1.0 (barrier)."""
    result = []
    for raw, t, b in zip(readings, track_ref, barrier_ref):
        span = b - t
        if span == 0:
            result.append(0.0)
        else:
            result.append(clamp((raw - t) / span, 0.0, 1.0))
    return result


def compute_edge_error(gs_norm: list[float]) -> float:
    """Compute edge error from normalized grayscale. Positive = drifting right.

    This is an error signal for the PD controller, not a steering angle.
    The PD controller converts positive error -> negative steering (steer left).
    """
    return gs_norm[2] - gs_norm[0]


class GateDetector:
    """Detect start/finish gate from grayscale deltas.

    Triggers on 2-of-3 sensors showing delta > threshold.
    Temporal confirmation: if only 1 triggers, waits up to confirm_frames
    for a 2nd. Debounce prevents double-counting.
    """

    def __init__(self, threshold: float, debounce_s: float = 3.0, confirm_frames: int = 3):
        self.threshold = threshold
        self.debounce_s = debounce_s
        self.confirm_frames = confirm_frames
        self._last_trigger_t: float = -999.0
        self._pending_count: int = 0
        self._pending_frames: int = 0

    def update(self, prev_gs: list[float], gs: list[float], t: float) -> bool:
        """Check if gate was crossed. Returns True on detection."""
        if (t - self._last_trigger_t) < self.debounce_s:
            self._pending_count = 0
            self._pending_frames = 0
            return False

        triggered_this_frame = sum(
            1 for p, c in zip(prev_gs, gs) if abs(c - p) > self.threshold
        )

        if self._pending_count > 0:
            self._pending_frames += 1
            self._pending_count += triggered_this_frame

            if self._pending_count >= 2:
                self._last_trigger_t = t
                self._pending_count = 0
                self._pending_frames = 0
                return True

            if self._pending_frames > self.confirm_frames:
                self._pending_frames = 0

        if triggered_this_frame >= 2:
            self._last_trigger_t = t
            self._pending_count = 0
            self._pending_frames = 0
            return True
        elif triggered_this_frame == 1:
            self._pending_count = 1
            self._pending_frames = 0

        return False


class TrackProfile:
    """Ordered list of track segments with persistence."""

    def __init__(self):
        self.segments: list[dict] = []
        self.map_speed: int = 20
        self.calibration_v: float = 0.0
        self.lap_duration_s: float = 0.0
        self.track_width_cm: float = 0.0
        self.lap_history: list[dict] = []

    def add_segment(self, seg_type: str, duration_s: float, width_left_cm: float,
                    width_right_cm: float, sonar_center_cm: float, gs_signature: list[float]) -> None:
        seg = {
            "id": len(self.segments),
            "type": seg_type,
            "duration_s": round(duration_s, 2),
            "width_left_cm": round(width_left_cm, 1),
            "width_right_cm": round(width_right_cm, 1),
            "sonar_center_cm": round(sonar_center_cm, 1),
            "race_speed": 28 if seg_type.startswith("turn") else 45,
            "steer_bias": 0,
            "entry_speed": 28 if seg_type.startswith("turn") else 45,
            "brake_before_s": 0.3 if seg_type.startswith("turn") else 0.0,
            "gs_signature": [round(v, 1) for v in gs_signature],
        }
        if seg_type.startswith("turn"):
            diff = width_right_cm - width_left_cm
            seg["steer_bias"] = round(clamp(diff * 0.5, -30, 30), 1)
        self.segments.append(seg)

    def save(self, path: Path) -> None:
        data = {
            "mapped_at": "",
            "map_speed": self.map_speed,
            "calibration_v": self.calibration_v,
            "lap_duration_s": self.lap_duration_s,
            "track_width_cm": self.track_width_cm,
            "segments": self.segments,
            "lap_history": self.lap_history,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "TrackProfile":
        data = json.loads(path.read_text())
        tp = cls()
        tp.map_speed = data.get("map_speed", 20)
        tp.calibration_v = data.get("calibration_v", 0.0)
        tp.lap_duration_s = data.get("lap_duration_s", 0.0)
        tp.track_width_cm = data.get("track_width_cm", 0.0)
        tp.segments = data.get("segments", [])
        tp.lap_history = data.get("lap_history", [])
        return tp


def classify_segment(left_cm: float, right_cm: float, center_cm: float, track_width_cm: float) -> str:
    """Classify a sensor reading as straight, turn_left, or turn_right."""
    half_width = track_width_cm / 2
    threshold = half_width * 0.20
    imbalance = abs(left_cm - right_cm)
    center_close = center_cm < track_width_cm

    if imbalance > threshold and center_close:
        return "turn_left" if left_cm < right_cm else "turn_right"
    return "straight"


SERVO_SETTLE_S = 0.15  # 150ms — matches px-wander


def safe_ping(px, retries: int = 1) -> float | None:
    """Read sonar with I2C retry. Returns cm or None."""
    for attempt in range(1 + retries):
        try:
            return px.get_distance()
        except OSError:
            if attempt < retries:
                time.sleep(0.03)
    return None


def safe_grayscale(px, retries: int = 1) -> list[float] | None:
    """Read grayscale with I2C retry. Returns [left, center, right] or None."""
    for attempt in range(1 + retries):
        try:
            return px.get_grayscale_data()
        except OSError:
            if attempt < retries:
                time.sleep(0.01)
    return None


def quick3_scan(px, settle_s: float = SERVO_SETTLE_S) -> tuple[float | None, float | None]:
    """Scan sonar at -25, 0, +25 degrees. Returns (left_cm, right_cm)."""
    readings: dict[int, float | None] = {}
    for angle in (-25, 0, 25):
        px.set_cam_pan_angle(angle)
        if settle_s > 0:
            time.sleep(settle_s)
        readings[angle] = safe_ping(px)
    px.set_cam_pan_angle(0)
    return readings.get(-25), readings.get(25)


MIN_RACE_SPEED = 5
MAX_SPEED_DELTA = 5


def apply_lap_learning(segment: dict, actual: dict, speed_ratio: float) -> dict:
    """Apply per-lap learning to a segment. Returns updated segment copy."""
    seg = dict(segment)
    if speed_ratio > 0:
        seg["duration_s"] = round(actual["duration_s"] / speed_ratio, 2)
    if actual.get("obstacle"):
        return seg
    if actual["wall_clips"] > 0:
        seg["race_speed"] = max(MIN_RACE_SPEED, seg["race_speed"] - MAX_SPEED_DELTA)
        seg["entry_speed"] = min(seg["entry_speed"], seg["race_speed"])
        if seg.get("brake_before_s", 0) > 0:
            seg["brake_before_s"] = round(seg["brake_before_s"] + 0.1, 2)
    else:
        seg["race_speed"] = seg["race_speed"] + 3
        seg["entry_speed"] = seg["race_speed"]
    return seg


def estop_threshold(speed: float) -> float:
    """Speed-dependent e-stop distance in cm."""
    return max(8.0, speed * 0.3)


def check_estop(sonar_cm: float | None, speed: float) -> bool:
    """Check if emergency stop should trigger."""
    if sonar_cm is None:
        return True
    return sonar_cm < estop_threshold(speed)


def check_edge_guard(gs_norm: list[float], threshold: float = 0.7) -> tuple[bool, float]:
    """Check if any grayscale sensor is near barrier.
    Returns (triggered, steer_correction).
    """
    left, _center, right = gs_norm
    if left > threshold:
        return True, 15.0
    if right > threshold:
        return True, -15.0
    return False, 0.0


class StuckDetector:
    """Detect if the car is stuck (sonar unchanged for timeout_s)."""

    def __init__(self, timeout_s: float = 2.0, tolerance_cm: float = 3.0):
        self.timeout_s = timeout_s
        self.tolerance_cm = tolerance_cm
        self._last_change_t: float = 0.0
        self._last_cm: float | None = None

    def update(self, sonar_cm: float | None, t: float) -> None:
        if sonar_cm is None:
            return
        if self._last_cm is None or abs(sonar_cm - self._last_cm) > self.tolerance_cm:
            self._last_cm = sonar_cm
            self._last_change_t = t

    def is_stuck(self, t: float) -> bool:
        return (t - self._last_change_t) > self.timeout_s


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
