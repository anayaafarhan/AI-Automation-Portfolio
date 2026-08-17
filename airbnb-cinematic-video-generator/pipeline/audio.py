"""Sound design.

No licensed music can be fetched automatically for $0 without either an API
(cost) or scraping (legally unsound), so the default is a locally
synthesized ambient pad — layered tones + soft pink noise, low-passed, with
a slow swell into the closing CTA. Zero licensing risk, zero cost. If you
drop a royalty-free track into music/, that's used instead (trimmed/looped
with fades, never re-hosted or fetched by this tool).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result.stdout.decode(errors="replace"))
        raise RuntimeError(f"ffmpeg command failed: {' '.join(cmd)}")


def find_user_music(music_dir: Path) -> Path | None:
    if not music_dir.exists():
        return None
    exts = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
    for p in sorted(music_dir.iterdir()):
        if p.suffix.lower() in exts:
            return p
    return None


def synthesize_ambient_music(duration: float, volume: float, out_path: Path) -> None:
    d = duration + 1.0
    swell_start = max(d - 4.0, 0.0)
    filt = (
        f"sine=frequency=98:duration={d}[a];"
        f"sine=frequency=146.83:duration={d}[b];"
        f"sine=frequency=196:duration={d}[c];"
        f"sine=frequency=293.66:duration={d}[e];"
        f"anoisesrc=color=pink:amplitude=0.018:duration={d}[n];"
        f"[a][b][c][e][n]amix=inputs=5:weights='1 0.75 0.5 0.3 0.45':normalize=0,"
        f"tremolo=f=0.12:d=0.25,"
        f"lowpass=f=1400,"
        f"afade=t=in:st=0:d=2.5,"
        f"volume='1+0.35*(t/{d})':eval=frame,"
        f"afade=t=out:st={max(d-2,0)}:d=2,"
        f"volume={volume}"
    )
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", filt,
        "-t", str(duration), "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ])


def prepare_audio(cfg: Config, duration: float, work_dir: Path) -> Path:
    music_dir = Path(cfg.music_dir)
    user_track = find_user_music(music_dir)
    out_path = work_dir / "audio.m4a"
    if user_track:
        print(f"  using your music track: {user_track.name}")
        run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(user_track), "-t", str(duration),
            "-af", f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(duration-1.5,0)}:d=1.5,volume={cfg.music_volume + 0.3}",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ])
    else:
        print("  no track in music/, synthesizing a free ambient pad locally")
        synthesize_ambient_music(duration, cfg.music_volume, out_path)
    return out_path


def mux_final(video: Path, audio: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(out_path),
    ])


def make_preview(final_video: Path, preview_path: Path) -> None:
    run([
        "ffmpeg", "-y", "-i", str(final_video),
        "-vf", "scale=720:1280",
        "-c:v", "libx264", "-preset", "fast", "-crf", "30",
        "-c:a", "aac", "-b:a", "128k",
        str(preview_path),
    ])
