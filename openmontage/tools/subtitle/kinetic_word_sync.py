"""PHASE C.7 — Word-level kinetic caption engine.

Uses faster-whisper (word-level timestamps) to produce an animated caption track:
a list of words, each with [start, end] seconds, plus a per-frame "active word index"
schedule suitable for driving word-highlight animations in a Remotion/subsurface player.

Output `data`:
  - words: [{word, start, end, index}]
  - cues:  aligned caption lines (grouped for display)
  - frame_schedule: for a given fps, the active word index per frame (for sync tests)

Verification: against real speech audio we check that word timestamps are monotonic and
that re-synthesizing the schedule recovers the spoken words in order (timing-sync test).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from tools.base_tool import BaseTool, ToolResult


def _group_lines(words: List[Dict[str, Any]], max_words: int = 6) -> List[List[int]]:
    """Group word indices into display lines of <= max_words for caption rendering."""
    lines, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if len(cur) >= max_words:
            lines.append(cur); cur = []
    if cur:
        lines.append(cur)
    return lines


class KineticWordSyncTool(BaseTool):
    name = "kinetic_word_sync"
    category = "subtitle"
    description = (
        "faster-whisper word-level timestamps -> animated caption track with per-word "
        "highlight windows and a frame-accurate active-word schedule."
    )
    params = {
        "audio_path": {"type": "str", "required": True, "help": "speech audio/video"},
        "model": {"type": "str", "default": "base",
                  "help": "faster-whisper model (tiny/base/small/...)"},
        "language": {"type": "str", "default": None, "help": "ISO code or None=auto"},
        "max_words_per_line": {"type": "int", "default": 6},
        "out_json": {"type": "str", "default": None, "help": "write caption track"},
        "fps": {"type": "int", "default": 30, "help": "fps for frame_schedule"},
        "device": {"type": "str", "default": "cpu"},
        "compute_type": {"type": "str", "default": "int8", "help": "int8 for CPU speed"},
    }

    def run(self, **p) -> ToolResult:
        from faster_whisper import WhisperModel

        if not os.path.exists(p["audio_path"]):
            return ToolResult(ok=False, error=f"missing {p['audio_path']}")

        model = WhisperModel(p["model"], device=p["device"],
                             compute_type=p["compute_type"])
        segments, info = model.transcribe(
            p["audio_path"], language=p["language"], word_timestamps=True,
            condition_on_previous_text=False)
        words: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        for seg in segments:
            if not seg.words:
                continue
            for w in seg.words:
                if w.word is None or w.start is None:
                    continue
                words.append({
                    "word": w.word.strip(),
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "index": len(words),
                })
                text_parts.append(w.word.strip())
        full_text = " ".join(text_parts)

        if not words:
            return ToolResult(ok=False, error="no words transcribed")

        # monotonicity check (timing integrity)
        mono = all(words[i]["start"] <= words[i]["end"] and
                   words[i]["start"] >= words[i - 1]["end"] - 0.05
                   for i in range(1, len(words)))

        lines = _group_lines(words, p["max_words_per_line"])

        # frame schedule: for each frame, which word index is "active" (being spoken)
        fps = p["fps"]
        last_t = words[-1]["end"]
        nframes = int(last_t * fps) + 1
        frame_schedule = []
        wi = 0
        for f in range(nframes):
            t = f / fps
            while wi < len(words) - 1 and words[wi]["end"] < t:
                wi += 1
            active = wi if words[wi]["start"] <= t <= words[wi]["end"] else -1
            frame_schedule.append(active)

        summary = {
            "language": getattr(info, "language", None),
            "words": len(words),
            "lines": len(lines),
            "duration_sec": round(last_t, 3),
            "monotonic_timestamps": bool(mono),
            "fps": fps,
        }
        data = {
            "summary": summary,
            "words": words,
            "lines": lines,
            "frame_schedule": frame_schedule,
            "text": full_text,
        }
        artifacts: Dict[str, str] = {}
        if p["out_json"]:
            with open(p["out_json"], "w") as fh:
                json.dump(data, fh)
            artifacts["json"] = p["out_json"]
        return ToolResult(
            ok=True, data=data, artifacts=artifacts,
            metrics={"words": len(words), "monotonic": bool(mono),
                     "duration_sec": summary["duration_sec"]},
        )
