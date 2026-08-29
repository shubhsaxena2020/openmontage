"""OpenMontage Kinetic Studio — automated beat-synced vertical shorts from gym footage.

Public API:
  from kinetic_studio import KineticStudio, KineticStudioConfig
  studio = KineticStudio(KineticStudioConfig())
  res = studio.run("gym.mp4", music="track.mp3", voiceover="coach.mp3")
  print(res.final_video)
"""
from kinetic_studio.config import (
    KineticStudioConfig, BrandSpec, OutputSpec, ReframeSpec, RampSpec,
    CaptionSpec, PoseSpec,
)
from kinetic_studio.orchestrator import KineticStudio, StudioRunResult, run_cli
from kinetic_studio.box_tracker import build_boxes

__all__ = [
    "KineticStudio", "KineticStudioConfig", "StudioRunResult", "run_cli",
    "BrandSpec", "OutputSpec", "ReframeSpec", "RampSpec", "CaptionSpec", "PoseSpec",
    "build_boxes",
]
