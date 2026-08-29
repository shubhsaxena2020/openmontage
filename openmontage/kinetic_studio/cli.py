"""Kinetic Studio CLI.

Usage (portable; runs on laptop or VPS):
  python -m kinetic_studio run INPUT.mp4 \
      [--music track.mp3] [--voiceover coach.mp3] \
      [--brand "FBC Arena"] [--config kinetic_studio_config.json] \
      [--workdir studio_out] [--out kinetic_short.mp4]

Also:
  python -m kinetic_studio init-config   -> writes a starter kinetic_studio_config.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# make the openmontage package importable when run as a module
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kinetic_studio.config import KineticStudioConfig  # noqa: E402
from kinetic_studio.orchestrator import KineticStudio, run_cli  # noqa: E402


def cmd_init_config(args):
    cfg = KineticStudioConfig()
    cfg.brand.name = "FBC Arena"
    cfg.brand.watermark_sub = "TRAIN HARD"
    cfg.brand.exercise = "FULL BODY"
    cfg.brand.exercise_detail = "HIGH ENERGY · BEAT SYNCED"
    out = args.out or "kinetic_studio_config.json"
    cfg.save(out)
    print(f"wrote starter config -> {out}")


def cmd_run(args):
    cfg = KineticStudioConfig.load(args.config) if args.config else KineticStudioConfig()
    if args.brand:
        cfg.brand.name = args.brand
    studio = KineticStudio(cfg, workdir=args.workdir)
    res = studio.run(args.input, music=args.music, voiceover=args.voiceover,
                     out_name=args.out)
    print("\n=== Kinetic Studio result ===")
    print(json.dumps(res.to_dict(), indent=2))
    if not res.ok:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kinetic_studio",
                                description="OpenMontage Kinetic Studio: gym footage -> beat-synced vertical short")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="process a video into a short")
    r.add_argument("input", help="input gym footage (.mp4)")
    r.add_argument("--music", help="optional music track (drives beat-sync)")
    r.add_argument("--voiceover", help="optional coach VO (drives kinetic captions)")
    r.add_argument("--brand", help="brand/watermark name")
    r.add_argument("--config", help="KineticStudioConfig json/yaml")
    r.add_argument("--workdir", default="studio_out")
    r.add_argument("--out", default="kinetic_short.mp4")
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("init-config", help="write a starter config file")
    i.add_argument("--out", default="kinetic_studio_config.json")
    i.set_defaults(func=cmd_init_config)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
