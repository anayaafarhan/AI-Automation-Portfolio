#!/usr/bin/env python3
"""
make_reel.py — one command, one folder of property assets in, one polished
cinematic vertical reel out.

    python3 make_reel.py                       # uses input/, config.json if present
    python3 make_reel.py --demo                # generates sample assets first
    python3 make_reel.py --config config.json --property-name "Sunset Villa"

Pipeline: analyze -> select & storyboard -> render camera-move clips
(or use real video directly) -> crossfade assembly -> color grade ->
music -> typography -> output/final_reel.mp4 + preview.mp4 + storyboard.json

100% local: Python + Pillow/numpy/scipy for analysis, ffmpeg for everything
video/audio. No paid APIs, no accounts, no uploads.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from pipeline.config import Config
    from pipeline.analysis import analyze_assets
    from pipeline.storyboard import build_storyboard, write_storyboard, load_storyboard
    from pipeline.motion import build_clip
    from pipeline.grade_assemble import concat_with_xfade, apply_grade, total_duration_with_xfade
    from pipeline.audio import prepare_audio, mux_final, make_preview
    from pipeline.typography import find_font, FONT_SERIF_CANDIDATES, FONT_SANS_CANDIDATES
    from pipeline.demo_assets import generate_demo_assets
except ImportError:
    sys.exit("Missing dependencies. Install with:\n    pip3 install -r requirements.txt")


def parse_args():
    ap = argparse.ArgumentParser(description="Generate a cinematic luxury property reel from a photo/video folder.")
    ap.add_argument("--input", default=None, help="Folder of property photos/videos (default: input/)")
    ap.add_argument("--music", default=None, help="Folder to check for a royalty-free track (default: music/)")
    ap.add_argument("--output", default=None, help="Output folder (default: output/)")
    ap.add_argument("--config", default=None, help="Path to a config.json (property name, location, amenities, CTA, style)")
    ap.add_argument("--property-name", default=None)
    ap.add_argument("--location", default=None)
    ap.add_argument("--amenities", default=None, help="Comma-separated, e.g. 'PRIVATE POOL,OCEAN VIEW,5 BEDROOMS'")
    ap.add_argument("--cta", default=None)
    ap.add_argument("--max-shots", type=int, default=None)
    ap.add_argument("--storyboard", default=None, help="Reuse/edit an existing storyboard.json instead of re-selecting")
    ap.add_argument("--font-serif", default=None)
    ap.add_argument("--font-sans", default=None)
    ap.add_argument("--no-sky-parallax", action="store_true")
    ap.add_argument("--no-grain", action="store_true")
    ap.add_argument("--demo", action="store_true", help="Generate a synthetic sample photo set into input/ before rendering")
    ap.add_argument("--keep-work-dir", action="store_true")
    return ap.parse_args()


def build_config(args) -> Config:
    cfg = Config.load(args.config)
    if args.input: cfg.input_dir = args.input
    if args.music: cfg.music_dir = args.music
    if args.output: cfg.output_dir = args.output
    if args.property_name is not None: cfg.property_name = args.property_name
    if args.location is not None: cfg.location = args.location
    if args.amenities is not None: cfg.amenities = [a.strip() for a in args.amenities.split(",") if a.strip()]
    if args.cta is not None: cfg.cta = args.cta
    if args.max_shots is not None: cfg.max_shots = args.max_shots
    if args.no_sky_parallax: cfg.sky_parallax = False
    if args.no_grain: cfg.film_grain = False
    return cfg


def main():
    args = parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH. Install it (it's free): https://ffmpeg.org/download.html")

    cfg = build_config(args)
    input_dir = Path(cfg.input_dir)
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        print("[demo] Generating synthetic sample property photos ...")
        generate_demo_assets(input_dir)
        if not cfg.property_name:
            cfg.property_name = "Casa Del Sol"
        if not cfg.location:
            cfg.location = "Malibu, California"
        if not cfg.amenities:
            cfg.amenities = ["PRIVATE POOL", "OCEAN VIEW", "3 BEDROOMS"]

    serif_font = find_font(FONT_SERIF_CANDIDATES, args.font_serif)
    sans_font = find_font(FONT_SANS_CANDIDATES, args.font_sans)

    work_dir = Path(tempfile.mkdtemp(prefix="cinematic_reel_"))
    try:
        storyboard_path = Path(args.storyboard) if args.storyboard else output_dir / "storyboard.json"

        if args.storyboard and Path(args.storyboard).exists():
            print(f"[1/6] Loading existing storyboard: {args.storyboard}")
            shots, meta = load_storyboard(Path(args.storyboard))
            cfg.property_name = cfg.property_name or meta.get("property_name", "")
            cfg.location = cfg.location or meta.get("location", "")
            cfg.cta = cfg.cta or meta.get("cta", "BOOK YOUR STAY")
        else:
            print(f"[1/6] Analyzing assets in {input_dir}/ (quality, exposure, outdoor/sky, room type) ...")
            assets = analyze_assets(input_dir, work_dir)
            for a in assets:
                tag = "video" if a.kind == "video" else "photo"
                print(f"       + {a.path.name:28s} [{tag:5s}] -> {a.category:14s} "
                      f"(quality {a.quality:5.2f}, outdoor {a.outdoor_conf:.2f})")

            print("[2/6] Building storyboard (selection, ordering, camera moves) ...")
            shots = build_storyboard(assets, cfg)
            write_storyboard(shots, cfg, storyboard_path)
            for s in shots:
                px = "+sky-parallax" if s.sky_parallax else ""
                cap = f" caption='{s.caption}'" if s.caption else ""
                print(f"       - {Path(s.path).name:28s} {s.category:14s} motion={s.motion}{px}{cap}")
            print(f"       storyboard written to {storyboard_path}")

        total_est = total_duration_with_xfade([s.duration for s in shots], cfg.transition_duration)
        print(f"       {len(shots)} shots, estimated runtime ~{total_est:.1f}s (target 20-30s)")

        print("[3/6] Rendering camera-move clips ...")
        clip_paths = []
        for i, shot in enumerate(shots):
            clip_paths.append(build_clip(shot, i, len(shots), work_dir, cfg, serif_font, sans_font))
            print(f"       clip {i+1}/{len(shots)} done")

        print("[4/6] Crossfade assembly + cinematic color grade ...")
        assembled = concat_with_xfade(clip_paths, [s.duration for s in shots], cfg, work_dir)
        graded = apply_grade(assembled, cfg, work_dir)

        print("[5/6] Sound design ...")
        audio_path = prepare_audio(cfg, total_est, work_dir)

        print("[6/6] Muxing final deliverables ...")
        final_path = output_dir / "final_reel.mp4"
        preview_path = output_dir / "preview.mp4"
        mux_final(graded, audio_path, final_path)
        make_preview(final_path, preview_path)

        print(f"\nDone.\n  {final_path.resolve()}\n  {preview_path.resolve()}\n  {storyboard_path.resolve()}")
    finally:
        if args.keep_work_dir:
            print(f"(intermediate files kept at {work_dir})")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
