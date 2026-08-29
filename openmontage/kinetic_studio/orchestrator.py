"""Kinetic Studio orchestrator.

Turns raw gym footage into a beat-synced vertical short by chaining the OpenMontage
toolkit:

  input.mp4
    -> extract audio (ffmpeg)                 [if no separate music/voiceover]
    -> beat_drop_mapper(audio)  -> beats.json
    -> motion_energy(video)     -> energy.json (highlight moments)
    -> fitness_pose(video)      -> pose.json   (reps/angles; optional)
    -> box_tracker(pose|motion) -> boxes.json  (athlete bbox for reframe)
    -> smart_reframe(video,boxes)-> reframed.mp4 (9:16, centred, anti-jitter)
    -> kinetic_ramper(reframed,beats) -> ramped.mp4 (tempo-synced to drops)
    -> kinetic_word_sync(voiceover|audio) -> captions.json (if captions enabled)
    -> Remotion StudioComposition(ramped + HUD + captions) -> final short.mp4
    -> mux music back under the short (ffmpeg)

Every step is resilient: a failure is recorded but does not abort the whole run (the
studio degrades gracefully — e.g. no captions if no speech, no pose if model missing).

Portable: pathlib paths, auto ffmpeg discovery, CUDA auto-detect. Runs headless on the
VPS for smoke-tests and on the laptop for production.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kinetic_studio.config import KineticStudioConfig
from kinetic_studio.box_tracker import build_boxes

# Import the toolkit (same package tree)
from tools import make_tool  # noqa: E402


def find_ffmpeg() -> str:
    """Locate ffmpeg: env FFMPEG_BIN -> PATH -> imageio-ffmpeg fallback."""
    env = os.environ.get("FFMPEG_BIN")
    if env and shutil.which(env):
        return env
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("ffmpeg not found (set FFMPEG_BIN or install ffmpeg)")


def device_auto(preferred: str) -> str:
    if preferred != "auto":
        return preferred
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


@dataclass
class StudioRunResult:
    ok: bool
    final_video: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    audio_used: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "final_video": self.final_video,
            "audio_used": self.audio_used, "error": self.error,
            "steps": self.steps,
        }


class KineticStudio:
    def __init__(self, config: KineticStudioConfig, workdir: Optional[str] = None,
                 ffmpeg: Optional[str] = None, verbose: bool = True):
        self.cfg = config
        self.work = Path(workdir or config.workdir).resolve()
        self.work.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = ffmpeg or find_ffmpeg()
        self.verbose = verbose
        self._log: List[Dict[str, Any]] = []

    def _step(self, name: str, ok: bool, detail: str = "", artifact: Optional[str] = None):
        self._log.append({"step": name, "ok": ok, "detail": detail, "artifact": artifact})
        if self.verbose:
            print(f"  [{('OK' if ok else 'FAIL')}] {name}: {detail}")

    # ---- helpers -------------------------------------------------------------
    def _extract_audio(self, video: str, out_wav: str) -> bool:
        try:
            subprocess.run([self.ffmpeg, "-y", "-i", video, "-vn", "-ac", "1",
                            "-ar", "22050", out_wav],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            self._step("extract_audio", False, str(e))
            return False

    def _mux_audio(self, video: str, audio: str, out: str) -> bool:
        try:
            subprocess.run([self.ffmpeg, "-y", "-i", video, "-i", audio,
                            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                            "-shortest", out],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            self._step("mux_audio", False, str(e))
            return False

    # ---- preview / proxy mode -------------------------------------------------
    PREVIEW_HEIGHT = 360  # proxy draft resolution (keeps 9:16 aspect)

    def render_dims(self) -> Dict[str, int]:
        """Output dimensions, dropping to proxy resolution when in preview mode.

        Dimensions are forced to even numbers because libx264 requires them (odd widths
        make ffmpeg exit and break the reframe pipe)."""
        w, h = self.cfg.output.width, self.cfg.output.height
        if self.cfg.preview:
            h = min(h, self.PREVIEW_HEIGHT)
            w = max(2, round(h * self.cfg.output.width / self.cfg.output.height))
        # force even (libx264 constraint)
        w = w - (w % 2)
        h = h - (h % 2)
        return {"width": w, "height": h}

    def should_render_studio(self) -> bool:
        """The Remotion HUD composite is skipped in preview mode (draft only)."""
        return (not self.cfg.preview) and (os.environ.get("KINETIC_HEADLESS") != "1")

    # ---- dry run -------------------------------------------------------------
    def dry_run(self, input_video: str, music: Optional[str] = None,
                voiceover: Optional[str] = None,
                out_name: str = "kinetic_short.mp4") -> Dict[str, Any]:
        """Compute the edit plan WITHOUT rendering (fast preview).

        Walks the same decision path as ``run`` but short-circuits before any ffmpeg
        render (reframe / ramper / Remotion / mux). It probes the clip for fps/duration,
        resolves the audio-sync anchors and the chosen preset's motion plan, and reports
        exactly which heavy steps ``run`` would perform. No output file is produced.

        Used by the CLI ``--dry-run`` flag. Pure with respect to rendering; the only
        side effects are reading the input file's metadata (cv2 probe) and listing the
        planned steps.
        """
        input_video = str(input_video)

        # clip probe (metadata only)
        fps = 30.0
        n_frames = 0
        duration = 0.0
        try:
            import cv2  # type: ignore
            cap = cv2.VideoCapture(input_video)
            _fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            _n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            fps = float(_fps) if _fps else 30.0
            n_frames = int(_n)
            duration = float(n_frames) / float(fps) if fps else 0.0
            cap.release()
        except Exception:
            pass

        # audio strategy (what run would do)
        audio = music or voiceover
        audio_strategy = (
            "use provided track" if audio else "extract from video (ffmpeg)"
        )

        # preset motion plan (pure) — what the ramper/zoom would follow.
        # Only build it when the clip was actually probed; otherwise report a note
        # instead of a degenerate plan with negative timestamps.
        preset_name = self.cfg.motion.name
        if n_frames > 0 and fps > 0:
            try:
                from kinetic_studio import presets as P
                motion_plan = P.build_motion_plan(
                    preset_name, int(fps), n_frames,
                    drop_times=None,
                    width=self.cfg.output.width, height=self.cfg.output.height)
            except Exception as e:  # preset missing -> still report the plan
                motion_plan = {"error": str(e)}
        else:
            motion_plan = {"note": "clip not probed (missing/unreadable); plan pending a valid input",
                           "preset": preset_name}

        # audio-sync anchors that run would resolve (beats + markers + voice peaks)
        anchors: List[float] = list(self.cfg.ramp.markers)
        if music or (voiceover is None):
            # beats come from the beat map; we list markers as the explicit anchors here
            pass

        dims = self.render_dims()
        plan = {
            "input": input_video,
            "out_name": out_name,
            "preview": self.cfg.preview,
            "output_dims": dims,
            "audio_strategy": audio_strategy,
            "audio_for_beats": bool(audio),
            "preset": preset_name,
            "motion_plan": motion_plan,
            "explicit_anchors": anchors,
            "steps": [
                {"step": "audio", "would_run": True,
                 "detail": audio_strategy},
                {"step": "beats", "would_run": bool(audio),
                 "detail": "beat_drop_mapper (librosa)" if audio else "skipped (no audio)"},
                {"step": "energy", "would_run": True,
                 "detail": "motion_energy (openCV diff)"},
                {"step": "pose", "would_run": self.cfg.pose.enabled,
                 "detail": "fitness_pose (YOLOv8, CPU)" if self.cfg.pose.enabled else "disabled"},
                {"step": "boxes", "would_run": True, "detail": "box_tracker"},
                {"step": "reframe", "would_run": True,
                 "detail": f"smart_reframe -> {dims['width']}x{dims['height']} (ffmpeg, RENDER)"},
                {"step": "captions", "would_run": bool(self.cfg.caption.enabled and voiceover),
                 "detail": "kinetic_word_sync (faster-whisper)" if voiceover else "no voiceover"},
                {"step": "ramper", "would_run": True,
                 "detail": "kinetic_ramper (ffmpeg setpts, RENDER)"},
                {"step": "studio_composite", "would_run": self.should_render_studio(),
                 "detail": "Remotion HUD (RENDER, browser)" if self.should_render_studio()
                           else "skipped (preview or no browser)"},
                {"step": "mux_music", "would_run": bool(music),
                 "detail": "mux music under short (ffmpeg)" if music else "no separate music"},
            ],
            "render_steps": [s["step"] for s in [
                {"step": "reframe"}, {"step": "ramper"},
                {"step": "studio_composite"} if self.should_render_studio() else {"step": "x"},
                {"step": "mux_music"} if music else {"step": "x"},
            ] if s["step"] != "x"],
        }
        return plan

    # ---- main ----------------------------------------------------------------
    def run(self, input_video: str, music: Optional[str] = None,
            voiceover: Optional[str] = None, out_name: str = "kinetic_short.mp4") -> StudioRunResult:
        input_video = str(input_video)
        dev = device_auto(self.cfg.pose.device)

        # 1) audio source
        audio = music or voiceover
        if audio is None:
            audio = str(self.work / "audio.wav")
            if not self._extract_audio(input_video, audio):
                audio = None
        self._step("audio", audio is not None, audio or "no audio available")
        audio_for_beats = audio

        # 2) beats
        beats_json = str(self.work / "beats.json")
        if audio_for_beats:
            r = make_tool("beat_drop_mapper", audio_path=audio_for_beats,
                          out_json=beats_json, drop_rel_thr=self.cfg.ramp.drop_rel_thr)
            self._step("beats", r.ok, str(r.metrics), beats_json if r.ok else None)
        else:
            r = None
            self._step("beats", False, "skipped (no audio)")
        beats_json = beats_json if (r and r.ok) else None

        # 3) motion energy (highlights)
        energy_json = str(self.work / "energy.json")
        r = make_tool("motion_energy", input_path=input_video, method="diff",
                      out_json=energy_json)
        self._step("energy", r.ok, str(r.metrics), energy_json if r.ok else None)
        energy_json = energy_json if (r and r.ok) else None

        # 4) pose (optional)
        pose_json = str(self.work / "pose.json")
        if self.cfg.pose.enabled:
            r = make_tool("fitness_pose", input_path=input_video,
                          model=self.cfg.pose.model, max_frames=self.cfg.pose.max_frames,
                          device=dev, out_json=pose_json)
            self._step("pose", r.ok, str(r.metrics), pose_json if r.ok else None)
            if not (r and r.ok):
                pose_json = None
        else:
            pose_json = None
            self._step("pose", True, "disabled by config")

        # 5) boxes for reframe
        boxes = build_boxes(input_video, pose_json)
        boxes_json = str(self.work / "boxes.json")
        with open(boxes_json, "w") as fh:
            json.dump(boxes, fh)
        self._step("boxes", len(boxes) > 0, f"{len(boxes)} boxes", boxes_json)

        # 6) smart reframe -> 9:16
        dims = self.render_dims()
        reframed = str(self.work / "reframed.mp4")
        r = make_tool("smart_reframe", input_path=input_video, boxes_json=boxes_json,
                      out_path=reframed, target_w=dims["width"], target_h=dims["height"],
                      alpha=self.cfg.reframe.alpha, deadband=self.cfg.reframe.deadband)
        self._step("reframe", r.ok, str(r.metrics), reframed if r.ok else None)
        if not (r and r.ok):
            return StudioRunResult(ok=False, steps=self._log,
                                   error="reframe failed", audio_used=audio)
        reframed = reframed if r.ok else None

        # 7) captions (if voiceover/speech present and enabled) — must run BEFORE the
        #    ramper so the ramper can sync slow-mo to speech onsets (voice peaks).
        captions_json = None
        if self.cfg.caption.enabled and voiceover:
            captions_json = str(self.work / "captions.json")
            r = make_tool("kinetic_word_sync", audio_path=voiceover,
                          model=self.cfg.caption.model, language=self.cfg.caption.language,
                          max_words_per_line=self.cfg.caption.max_words_per_line,
                          out_json=captions_json)
            self._step("captions", r.ok, str(r.metrics), captions_json if r.ok else None)
            captions_json = captions_json if (r and r.ok) else None
        else:
            self._step("captions", True, "disabled / no voiceover")

        # 8) kinetic ramper (tempo sync to beats + markers + voice peaks from captions)
        ramped = str(self.work / "ramped.mp4")
        # derive voice-peak anchors from caption word onsets (when captions are enabled)
        voice_peaks: List[float] = []
        if captions_json and os.path.exists(captions_json):
            try:
                with open(captions_json) as fh:
                    _cap = json.load(fh)
                voice_peaks = [w["start"] for w in _cap.get("words", []) if "start" in w]
            except Exception:
                voice_peaks = []
        r = make_tool("kinetic_ramper", input_path=reframed, map_json=beats_json,
                      marker_times=",".join(str(m) for m in self.cfg.ramp.markers) or None,
                      voice_peaks=",".join(str(v) for v in voice_peaks) or None,
                      out_path=ramped, setup_speed=self.cfg.ramp.setup_speed,
                      peak_speed=self.cfg.ramp.peak_speed,
                      snap_tolerance=self.cfg.ramp.snap_tolerance)
        self._step("ramper", r.ok, str(r.metrics), ramped if r.ok else None)
        ramped = ramped if (r and r.ok) else reframed
        assert ramped is not None, "reframed must exist at this point"

        # 9) Remotion final composite (HUD + kinetic captions over ramped video)
        final = str(self.work / out_name)
        remotion_ok = self.should_render_studio() and self._render_studio(ramped, captions_json, final)
        if not remotion_ok:
            self._step("studio_composite", False, "Remotion render unavailable; "
                       "using ramped.mp4 as final", ramped)
            final = ramped
        else:
            self._step("studio_composite", True, "rendered short", final)

        # 10) mux music back under the short (if separate music provided)
        if music and final:
            muxed = str(self.work / "final_with_music.mp4")
            if self._mux_audio(final, music, muxed):
                final = muxed
                self._step("mux_music", True, "music added", final)
            else:
                self._step("mux_music", False, "kept short without music", final)

        ok = final is not None and os.path.exists(final)
        return StudioRunResult(ok=ok, final_video=final, steps=self._log,
                               audio_used=audio)

    # ---- Remotion bridge -----------------------------------------------------
    @staticmethod
    def _composition_fps(requested: Optional[int]) -> int:
        """The fps the Remotion composition is rendered at.

        Uses the requested fps from config; only falls back to 30 when none was
        provided. This is the regression anchor for the fps-hardcoding bug: the renderer
        must honor the configured fps (e.g. 60) and never bake in a default.
        """
        return int(requested) if requested else 30

    def _build_studio_input(self, bg_name: str, cap_data: Optional[dict],
                            n_frames: int) -> Dict[str, Any]:
        """Assemble the studio_input.json payload the Remotion composite consumes.

        Pure with respect to rendering: building this dict does NOT require a browser, so
        it is unit-testable on the VPS. fps/dims come from config (via _composition_fps),
        proving the composer is driven by config, not a hard-coded default.
        """
        words = cap_data["words"] if cap_data else []
        frame_schedule = cap_data["frame_schedule"] if cap_data else []
        return {
            "video": bg_name,
            "brand": self.cfg.brand.name,
            "accent": self.cfg.brand.accent,
            "watermark_sub": self.cfg.brand.watermark_sub,
            "exercise": self.cfg.brand.exercise,
            "exercise_detail": self.cfg.brand.exercise_detail,
            "words": words,
            "frame_schedule": frame_schedule,
            "fps": self._composition_fps(self.cfg.output.fps),
            "width": self.cfg.output.width,
            "height": self.cfg.output.height,
            "durationInFrames": max(60, n_frames or (len(frame_schedule) if cap_data else 300)),
        }

    def _render_studio(self, video_path: str, captions_json: Optional[str],
                       out_path: str) -> bool:
        remotion_dir = Path(__file__).resolve().parent.parent / "remotion"
        if not (remotion_dir / "package.json").exists():
            self._step("studio_composite", False, "remotion/ not found; skipping")
            return False
        public = remotion_dir / "public"
        public.mkdir(exist_ok=True)
        # Remotion's headless Chromium decodes H.264 reliably but NOT OpenCV's mp4v
        # (MPEG-4 Part 2) codec -> "no supported streams". Transcode the background to
        # H.264 so both the headless render here and `remotion studio` on the laptop work.
        bg = public / "studio_bg.mp4"
        try:
            subprocess.run([self.ffmpeg, "-y", "-i", video_path, "-an",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-preset", "veryfast", str(bg)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self._step("studio_composite", False, f"transcode failed: {e}")
            return False
        if not bg.exists():
            self._step("studio_composite", False, "transcoded bg missing")
            return False
        # Probe real frame count so the Composition duration matches the footage
        # (Remotion errors if --frames exceeds the media length).
        n_frames = 0
        try:
            import cv2  # type: ignore
            cap = cv2.VideoCapture(str(bg))
            n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
        except Exception:
            n_frames = 0
        cap_data = None
        if captions_json and os.path.exists(captions_json):
            with open(captions_json) as fh:
                cap_data = json.load(fh)
        studio_input = self._build_studio_input(bg.name, cap_data, n_frames)
        with open(remotion_dir / "studio_input.json", "w") as fh:
            json.dump(studio_input, fh)
        try:
            env = dict(os.environ)
            env["PATH"] = str(remotion_dir / "node_modules" / ".bin") + os.pathsep + env.get("PATH", "")
            # Render the full composition. Pass studio_input.json as --props so the
            # runtime brand/caption/duration values are used (calculateMetadata derives
            # durationInFrames from props; the static import is only a fallback).
            props_path = (remotion_dir / "studio_input.json").resolve()
            subprocess.run(
                [str(remotion_dir / "node_modules" / ".bin" / "remotion"), "render",
                 "src/studio-entry.tsx", "StudioComposition", str(out_path),
                 f"--props={props_path}"],
                cwd=str(remotion_dir), env=env, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return os.path.exists(out_path)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode(errors="replace")[-1500:]
            self._step("studio_composite", False, f"render error: {err}")
            return False
        except Exception as e:
            self._step("studio_composite", False, f"render error: {e}")
            return False


def run_cli(input_video: str, **opts) -> StudioRunResult:
    cfg = opts.pop("config", None)
    if isinstance(cfg, str):
        config = KineticStudioConfig.load(cfg)
    elif isinstance(cfg, KineticStudioConfig):
        config = cfg
    else:
        config = KineticStudioConfig()
    if opts.get("brand"):
        config.brand.name = opts["brand"]
    studio = KineticStudio(config, workdir=opts.get("workdir"))
    return studio.run(input_video, music=opts.get("music"),
                      voiceover=opts.get("voiceover"),
                      out_name=opts.get("out", "kinetic_short.mp4"))
