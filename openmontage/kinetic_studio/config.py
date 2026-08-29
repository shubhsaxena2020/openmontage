"""Kinetic Studio configuration.

A single dataclass holds every knob the studio needs to turn raw gym footage into a
beat-synced vertical short. It loads from JSON (and YAML if PyYAML is present) so the
same config that drives a headless VPS smoke-test also drives the laptop production run.

All paths are resolved as pathlib.Path and may be absolute or relative to a `base_dir`.
This keeps the package OS-portable (Windows vs Linux).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class OutputSpec:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    codec: str = "libx264"
    crf: int = 20


@dataclass
class BrandSpec:
    name: str = "FBC Arena"
    accent: str = "#22d3ee"      # HUD highlight color
    watermark_sub: str = "TRAIN HARD"   # small tagline under the badge
    exercise: str = "WORKOUT"    # default exercise name card text
    exercise_detail: str = "FULL BODY · HIGH ENERGY"


@dataclass
class ReframeSpec:
    target_w: int = 540          # 540 wide -> 540x960 crop area inside 1080x1920
    alpha: float = 0.25          # EMA smoothing factor (lower = smoother)
    deadband: int = 6            # px dead-band before recentre (anti-jitter)


@dataclass
class RampSpec:
    setup_speed: float = 1.6     # speed-up during low-energy setup
    peak_speed: float = 0.4      # slow-mo on peak lifts / drops
    drop_rel_thr: float = 1.25   # relative energy jump => "drop"
    markers: List[float] = field(default_factory=list)  # explicit anchor seconds (sync)
    snap_tolerance: float = 0.05 # seconds; anchors within this of a frame grid are snapped


@dataclass
class CaptionSpec:
    enabled: bool = True
    model: str = "base"          # faster-whisper model
    language: Optional[str] = "en"
    max_words_per_line: int = 5
    highlight_color: str = "#fde047"
    theme: str = "default"       # "default" | "caption" (Phase E.20 caption-style HUD variant)


@dataclass
class PoseSpec:
    enabled: bool = True
    model: str = "yolov8n-pose.pt"
    max_frames: int = 0          # 0 = all
    device: str = "auto"         # auto -> cuda if available else cpu


@dataclass
class MotionPresetSpec:
    name: str = "cinematic"     # key into kinetic_studio.presets.PRESETS
    apply_zoom: bool = True     # include the preset's Ken-Burns zoom keyframes
    apply_transition: bool = True


@dataclass
class KineticStudioConfig:
    brand: BrandSpec = field(default_factory=BrandSpec)
    output: OutputSpec = field(default_factory=OutputSpec)
    reframe: ReframeSpec = field(default_factory=ReframeSpec)
    ramp: RampSpec = field(default_factory=RampSpec)
    caption: CaptionSpec = field(default_factory=CaptionSpec)
    pose: PoseSpec = field(default_factory=PoseSpec)
    motion: MotionPresetSpec = field(default_factory=MotionPresetSpec)
    preview: bool = False          # proxy/draft mode: low-res, skip HUD composite, faster
    workdir: str = "studio_out"  # where intermediates + final short land

    # --- (de)serialization ---------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KineticStudioConfig":
        return cls(
            brand=BrandSpec(**(d.get("brand") or {})),
            output=OutputSpec(**(d.get("output") or {})),
            reframe=ReframeSpec(**(d.get("reframe") or {})),
            ramp=RampSpec(**(d.get("ramp") or {})),
            caption=CaptionSpec(**(d.get("caption") or {})),
            pose=PoseSpec(**(d.get("pose") or {})),
            motion=MotionPresetSpec(**(d.get("motion") or {})),
            workdir=d.get("workdir", "studio_out"),
        )

    @classmethod
    def load(cls, path: str) -> "KineticStudioConfig":
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if path.endswith((".yaml", ".yml")):
            try:
                import yaml  # type: ignore
                return cls.from_dict(yaml.safe_load(text))
            except ImportError:
                raise RuntimeError("PyYAML not installed; use a .json config")
        return cls.from_dict(json.loads(text))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)


# A small default config the CLI can emit so users have a starting point.
DEFAULT_CONFIG_PATH = "kinetic_studio_config.json"
