"""Anime and velocity visual effects compositor tool.

Applies chromatic aberration, RGB split glitching, anime bloom/glow,
zoom punch-in, screen shake, 35mm film grain, vignette, letterbox,
impact flash, and 3D LUT color grading via a single-pass FFmpeg filtergraph.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class AnimeFX(BaseTool):
    name = "anime_fx"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "ffmpeg"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:ffmpeg"]
    install_instructions = "Install FFmpeg: https://ffmpeg.org/download.html"
    agent_skills = ["ffmpeg", "color-grading", "anime-fx"]

    capabilities = [
        "chromatic_aberration",
        "rgb_split",
        "anime_glow",
        "zoom_punch",
        "screen_shake",
        "film_grain",
        "vignette",
        "letterbox",
        "impact_flash",
        "lut_color_grade",
    ]
    supports = {
        "offline": True,
        "single_pass_filtergraph": True,
        "tetrahedral_lut": True,
    }
    best_for = [
        "anime velocity edits",
        "phonk visual styling",
        "impact beat flashes",
        "cinematic bloom",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path", "output_path"],
        "properties": {
            "video_path": {"type": "string"},
            "output_path": {"type": "string"},
            "target_resolution": {
                "type": "string",
                "default": "source",
                "description": 'Target video resolution such as "1080x1920" or "source".',
            },
            "chromatic_aberration": {"type": "boolean", "default": False},
            "rgb_split": {"type": "boolean", "default": False},
            "glow": {"type": "boolean", "default": False},
            "zoom_punch": {"type": "boolean", "default": False},
            "screen_shake": {"type": "boolean", "default": False},
            "film_grain": {"type": "boolean", "default": False},
            "vignette": {"type": "boolean", "default": False},
            "letterbox": {"type": "boolean", "default": False},
            "impact_flash": {"type": "boolean", "default": False},
            "flash_times": {
                "type": "array",
                "items": {"type": "number"},
                "default": [],
            },
            "lut": {"type": ["string", "null"], "default": None},
            "lut_strength": {"type": "number", "default": 1.0},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=1024, vram_mb=0, disk_mb=500, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = [
        "video_path",
        "target_resolution",
        "chromatic_aberration",
        "rgb_split",
        "glow",
        "zoom_punch",
        "screen_shake",
        "film_grain",
        "vignette",
        "letterbox",
        "impact_flash",
        "lut",
    ]
    side_effects = ["writes output video to output_path"]
    user_visible_verification = ["Inspect output video for applied visual effects and color grading"]

    def get_status(self) -> ToolStatus:
        if shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    @staticmethod
    def _probe_video_resolution(video_path: str) -> tuple[int, int]:
        width = 0
        height = 0
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                video_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                payload = json.loads(res.stdout)
                streams = payload.get("streams", [])
                if streams:
                    width = int(streams[0].get("width", 0) or 0)
                    height = int(streams[0].get("height", 0) or 0)
        except Exception:
            pass
        return width, height

    @classmethod
    def _resolve_target_resolution(cls, target_resolution: str, video_path: str) -> tuple[int, int]:
        value = (target_resolution or "source").strip().lower()
        if value == "source":
            return cls._probe_video_resolution(video_path)

        parts = value.split("x", 1)
        if len(parts) == 2:
            try:
                width = int(parts[0])
                height = int(parts[1])
                if width > 0 and height > 0:
                    return width, height
            except ValueError:
                pass

        return cls._probe_video_resolution(video_path)

    @staticmethod
    def _resolve_lut_path(lut_name: str | None) -> Path | None:
        """Resolve LUT by name or path against assets/editing/luts directory."""
        if not lut_name:
            return None
        candidate = Path(lut_name)
        if candidate.is_file():
            return candidate

        # Check in project assets/editing/luts
        project_root = Path(__file__).resolve().parent.parent.parent
        luts_dir = project_root / "assets" / "editing" / "luts"

        clean_name = lut_name.strip()
        if not clean_name.endswith(".cube"):
            clean_name += ".cube"

        target = luts_dir / clean_name
        if target.is_file():
            return target

        # Check by stem match
        for f in luts_dir.glob("*.cube"):
            if f.stem.lower() == lut_name.lower().replace(".cube", ""):
                return f
        return None

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path_raw = inputs.get("video_path")
        output_path_raw = inputs.get("output_path")
        if not video_path_raw or not output_path_raw:
            return ToolResult(success=False, error="Missing required input 'video_path' or 'output_path'")

        video_path = str(Path(video_path_raw).resolve())
        output_path = str(Path(output_path_raw).resolve())

        if not Path(video_path).is_file():
            return ToolResult(success=False, error=f"Input video file not found: {video_path}")

        chromatic_aberration = bool(inputs.get("chromatic_aberration", False))
        rgb_split = bool(inputs.get("rgb_split", False))
        glow = bool(inputs.get("glow", False))
        zoom_punch = bool(inputs.get("zoom_punch", False))
        screen_shake = bool(inputs.get("screen_shake", False))
        film_grain = bool(inputs.get("film_grain", False))
        vignette = bool(inputs.get("vignette", False))
        letterbox = bool(inputs.get("letterbox", False))
        impact_flash = bool(inputs.get("impact_flash", False))
        flash_times = [float(t) for t in inputs.get("flash_times", [])]
        lut = inputs.get("lut")
        target_resolution = str(inputs.get("target_resolution", "source"))
        target_width, target_height = self._resolve_target_resolution(target_resolution, video_path)
        if target_width <= 0 or target_height <= 0:
            target_width, target_height = 1920, 1080

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        effects_applied: list[str] = []
        filter_steps: list[str] = []
        node_idx = 0
        current_node = "[0:v]"

        # Helper to advance node names
        def next_node() -> str:
            nonlocal node_idx
            node_idx += 1
            return f"[v{node_idx}]"

        # 1. Zoom Punch
        if zoom_punch:
            out_node = next_node()
            filter_steps.append(
                f"{current_node}crop=w='iw/(1 + 0.35*exp(-0.15*mod(n,30)))':"
                f"h='ih/(1 + 0.35*exp(-0.15*mod(n,30)))':"
                f"x='(in_w-out_w)/2':y='(in_h-out_h)/2',"
                f"scale={target_width}:{target_height}:flags=lanczos{out_node}"
            )
            current_node = out_node
            effects_applied.append("zoom_punch")

        # 2. Screen Shake
        if screen_shake:
            out_node = next_node()
            filter_steps.append(
                f"{current_node}crop=w=iw-40:h=ih-40:"
                f"x='20 + 15*sin(n*1.8)*sin(n*0.7)':y='20 + 15*cos(n*1.4)*cos(n*0.5)',"
                f"scale={target_width}:{target_height}:flags=bicubic{out_node}"
            )
            current_node = out_node
            effects_applied.append("screen_shake")

        # 3. Chromatic Aberration
        if chromatic_aberration:
            out_node = next_node()
            # Keep the static aberration subtle; use integer offsets only.
            filter_steps.append(f"{current_node}rgbashift=rh=4:bh=-4:edge=wrap{out_node}")
            current_node = out_node
            effects_applied.append("chromatic_aberration")

        # 4. RGB Split Glitch
        if rgb_split:
            out_node = next_node()
            if flash_times:
                pulse_terms = " + ".join(
                    [
                        f"if(between(t,{t:.2f},{t + 0.15:.2f}),sin((t-{t:.2f})*PI/0.15),0)"
                        for t in flash_times[:12]
                    ]
                )
                pulse_expr = f"({pulse_terms})" if pulse_terms else "0"
                r_in = next_node()
                g_in = next_node()
                b_in = next_node()
                rg = next_node()

                filter_steps.append(f"{current_node}split=3{r_in}{g_in}{b_in}")
                filter_steps.append(f"{r_in}lutrgb=g=0:b=0[rr]")
                filter_steps.append(f"{g_in}lutrgb=r=0:b=0[gg]")
                filter_steps.append(f"{b_in}lutrgb=r=0:g=0[bb]")
                filter_steps.append(
                    f"[gg][rr]overlay=x='12*{pulse_expr}':y=0:format=auto{rg}"
                )
                filter_steps.append(
                    f"{rg}[bb]overlay=x='-12*{pulse_expr}':y=0:format=auto{out_node}"
                )
            else:
                filter_steps.append(f"{current_node}rgbashift=rh=6:bh=-6:edge=wrap{out_node}")
            current_node = out_node
            effects_applied.append("rgb_split")

        # 5. Glow / Bloom
        if glow:
            out_node = next_node()
            base = next_node()
            highlight = next_node()
            bloom = next_node()

            filter_steps.append(f"{current_node}split=2{base}{highlight}")
            filter_steps.append(
                f"{highlight}lutyuv=y='val-16':u='128':v='128',curves=all='0/0 0.6/0 0.85/0.7 1/1',gblur=sigma=28:steps=3{bloom}"
            )
            filter_steps.append(f"{base}{bloom}blend=all_mode=screen:all_opacity=0.75{out_node}")
            current_node = out_node
            effects_applied.append("glow")

        # 6. Impact Flash
        if impact_flash:
            out_node = next_node()
            if flash_times:
                flash_expr = " + ".join(
                    [f"between(t,{t:.2f},{t + 0.20:.2f})" for t in flash_times[:12]]
                )
                filter_steps.append(
                    f"{current_node}drawbox=x=0:y=0:w=iw:h=ih:color=white@0.85:t=fill:enable='{flash_expr}'{out_node}"
                )
            else:
                filter_steps.append(
                    f"{current_node}drawbox=x=0:y=0:w=iw:h=ih:color=white@0.85:t=fill:enable='between(t,1.0,1.25)'{out_node}"
                )
            current_node = out_node
            effects_applied.append("impact_flash")

        # 7. Film Grain
        if film_grain:
            out_node = next_node()
            filter_steps.append(f"{current_node}noise=alls=14:allf=t+u{out_node}")
            current_node = out_node
            effects_applied.append("film_grain")

        # 8. Vignette
        if vignette:
            out_node = next_node()
            filter_steps.append(f"{current_node}vignette=angle=PI/4.5:aspect=16/9{out_node}")
            current_node = out_node
            effects_applied.append("vignette")

        # 9. 3D LUT
        lut_path = self._resolve_lut_path(lut)
        if lut_path and lut_path.is_file():
            out_node = next_node()
            escaped_lut = str(lut_path).replace("\\", "/").replace(":", "\\:")
            filter_steps.append(f"{current_node}lut3d=file='{escaped_lut}':interp=tetrahedral{out_node}")
            current_node = out_node
            effects_applied.append(f"lut:{lut_path.stem}")

        # 10. Letterbox
        if letterbox:
            out_node = next_node()
            filter_steps.append(
                f"{current_node}crop=iw:'ih*(1/(2.39/(16/9)))':0:'(ih - ih*(1/(2.39/(16/9))))/2',"
                f"pad={target_width}:{target_height}:0:'({target_height}-out_h)/2':black{out_node}"
            )
            current_node = out_node
            effects_applied.append("letterbox")

        # If no filters were enabled, simple null / passthrough
        if not filter_steps:
            out_node = next_node()
            filter_steps.append(f"{current_node}null{out_node}")
            current_node = out_node
            effects_applied.append("passthrough")

        out_node = next_node()
        filter_steps.append(f"{current_node}fps=60{out_node}")
        current_node = out_node

        filtergraph = ";".join(filter_steps)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-filter_complex", filtergraph,
            "-map", current_node,
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=f"AnimeFX rendering failed (exit {proc.returncode}): {proc.stderr}",
                duration_seconds=round(time.time() - start_time, 2),
            )

        if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
            return ToolResult(success=False, error=f"AnimeFX output file missing or empty: {output_path}")

        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "filtergraph": filtergraph,
                "effects_applied": effects_applied,
            },
            artifacts=[output_path],
            duration_seconds=round(time.time() - start_time, 2),
        )
