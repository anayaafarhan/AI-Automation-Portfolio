"""Crossfade assembly + cinematic color grade.

Transitions are deliberately a single restrained crossfade style throughout
(no alternating wipes/spins) — the brief was elegance and restraint, not a
transitions showcase. The grade is a light, luxury-leaning treatment: gentle
S-curve contrast, a touch of teal/orange separation, a light vignette, and
optional fine film grain — all standard ffmpeg filters, applied once to the
whole assembled sequence so the look is consistent shot-to-shot.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Config


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result.stdout.decode(errors="replace"))
        raise RuntimeError(f"ffmpeg command failed: {' '.join(cmd)}")


def total_duration_with_xfade(durations: list[float], xfade: float) -> float:
    if not durations:
        return 0.0
    total = durations[0]
    for d in durations[1:]:
        total += d - xfade
    return total


def concat_with_xfade(clips: list[Path], durations: list[float], cfg: Config, work_dir: Path) -> Path:
    out_path = work_dir / "video_concat.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], out_path)
        return out_path

    xfade = cfg.transition_duration
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    filter_parts = []
    cumulative = durations[0]
    prev_label = "0"
    for i in range(1, len(clips)):
        offset = cumulative - xfade
        cur_label = f"v{i}"
        filter_parts.append(
            f"[{prev_label}][{i}]xfade=transition={cfg.transition}:"
            f"duration={xfade}:offset={offset:.3f}[{cur_label}]"
        )
        prev_label = cur_label
        cumulative = cumulative + durations[i] - xfade

    filter_complex = ";".join(filter_parts)
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex, "-map", f"[{prev_label}]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
        str(out_path),
    ])
    return out_path


def grade_filter_chain(cfg: Config) -> str:
    s = max(0.0, cfg.grade_strength)
    if s == 0:
        return "null"
    parts = [
        "curves=preset=medium_contrast",
        f"eq=saturation={1 + 0.08*s:.3f}:contrast={1 + 0.03*s:.3f}",
        f"colorbalance=rs={0.03*s:.3f}:bs={-0.03*s:.3f}:rm={0.02*s:.3f}:bm={-0.02*s:.3f}:rh={0.04*s:.3f}:bh={-0.02*s:.3f}",
        f"vignette=PI/{max(5.0, 7-s):.2f}",
    ]
    if cfg.film_grain:
        parts.append(f"noise=alls={max(2,int(4*s))}:allf=t")
    return ",".join(parts)


def apply_grade(video: Path, cfg: Config, work_dir: Path) -> Path:
    out_path = work_dir / "video_graded.mp4"
    run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", grade_filter_chain(cfg),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18",
        str(out_path),
    ])
    return out_path
