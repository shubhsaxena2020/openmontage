"""OpenMontage tools package — importing this registers all tools in the registry
and re-exports the base classes + registry helpers."""
from tools.base_tool import (
    BaseTool, ToolResult, register, get_tool, list_tools, make_tool,
)
from tools.analysis.fitness_pose import FitnessPoseTool
from tools.analysis.motion_energy import MotionEnergyTool
from tools.video.smart_reframe import SmartReframeTool
from tools.video.kinetic_ramper import KineticRamperTool
from tools.audio.beat_drop_mapper import BeatDropMapperTool
from tools.audio.audio_master_duck import AudioMasterDuckTool
from tools.subtitle.kinetic_word_sync import KineticWordSyncTool

__all__ = [
    "BaseTool", "ToolResult", "register", "get_tool", "list_tools", "make_tool",
    "FitnessPoseTool", "MotionEnergyTool", "SmartReframeTool",
    "KineticRamperTool", "BeatDropMapperTool", "AudioMasterDuckTool", "KineticWordSyncTool",
]
