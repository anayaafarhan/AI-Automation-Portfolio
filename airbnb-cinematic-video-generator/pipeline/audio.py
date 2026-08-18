"""Sound design.

No licensed music can be fetched automatically for $0 without either an API
(cost) or scraping (legally unsound), so the default is a locally
synthesized ambient pad — layered tones + soft pink noise, low-passed, with
a slow swell into the closing CTA. Zero licensing risk, zero cost. If you
drop a royalty-free track into music/, that's used instead (trimmed/looped
with fades, never re-hosted or fetched by this tool).

On top of the music bed, layer_soundscape() adds a second, environmental
layer keyed to what's actually on screen: a soft water texture under pool
shots, gentle outdoor air under exterior/view shots, near-silent room tone
under interiors, a subtle whoosh at each cut, and a very low sub-bass
undercurrent for cinematic weight. All of it is synthesized locally with
ffmpeg's audio sources/filters — no samples, no downloads, no licensing
risk — and kept deliberately quiet: it should read as "the space has air
and texture," not as sound effects.
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
        "-t", str(duration), "-ac", "2", "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ])


def prepare_audio(cfg: Config, duration: float, work_dir: Path) -> Path:
    music_dir = Path(cfg.music_dir)
    user_track = find_user_music(music_dir)
    out_path = work_dir / "music.m4a"
    if user_track:
        print(f"  using your music track: {user_track.name}")
        run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(user_track), "-t", str(duration),
            "-af", f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(duration-1.5,0)}:d=1.5,volume={cfg.music_volume + 0.3}",
            "-ac", "2", "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ])
    else:
        print("  no track in music/, synthesizing a free ambient pad locally")
        synthesize_ambient_music(duration, cfg.music_volume, out_path)
    return out_path


# ---------------------------------------------------------------------------
# Environmental layer: ambience keyed to shot category, whoosh at cuts,
# sub-bass undercurrent — all synthesized, mixed under the music bed.
# ---------------------------------------------------------------------------

def _ambience_kind(category: str) -> str:
    if category == "Pool":
        return "water"
    if category in ("Exterior", "View", "Golden Hour", "Garden"):
        return "outdoor"
    return "room"


def _ambience_segment_filter(kind: str, dur: float) -> str:
    d = round(dur, 3)
    if kind == "water":
        return (
            f"anoisesrc=color=white:amplitude=0.05:duration={d},"
            f"bandpass=f=1200:width_type=h:w=800,"
            f"tremolo=f=2.2:d=0.5,volume=0.30"
        )
    if kind == "outdoor":
        return (
            f"anoisesrc=color=pink:amplitude=0.045:duration={d},"
            f"highpass=f=300,lowpass=f=4000,"
            f"tremolo=f=0.18:d=0.3,volume=0.20"
        )
    return (  # near-silent interior room tone
        f"anoisesrc=color=brown:amplitude=0.02:duration={d},"
        f"lowpass=f=800,volume=0.09"
    )


def _transition_offsets(durations: list[float], xfade: float) -> list[float]:
    if len(durations) < 2:
        return []
    offsets = []
    cumulative = durations[0]
    for d in durations[1:]:
        offsets.append(cumulative - xfade)
        cumulative += d - xfade
    return offsets


def build_ambience_bed(shots, xfade: float, work_dir: Path) -> Path:
    """One continuous ambience track, category-matched per shot and
    crossfaded at exactly the same points/duration as the picture cuts."""
    out_path = work_dir / "ambience.wav"
    segments = [_ambience_segment_filter(_ambience_kind(s.category), s.duration) for s in shots]

    if len(segments) == 1:
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", segments[0], "-ac", "2", "-c:a", "pcm_s16le", str(out_path)])
        return out_path

    inputs = []
    for seg in segments:
        inputs += ["-f", "lavfi", "-i", seg]
    parts = []
    prev = "0:a"
    for i in range(1, len(segments)):
        cur = f"a{i}"
        parts.append(f"[{prev}][{i}:a]acrossfade=d={xfade}:c1=tri:c2=tri[{cur}]")
        prev = cur
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(parts), "-map", f"[{prev}]",
        "-ac", "2", "-c:a", "pcm_s16le", str(out_path),
    ])
    return out_path


def build_whoosh_track(offsets: list[float], total_duration: float, work_dir: Path) -> Path:
    """A soft, filtered noise-burst placed at each cut — subtle scene-change
    punctuation, not a sound effect you consciously notice."""
    out_path = work_dir / "whoosh.wav"
    if not offsets:
        run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration}",
            "-c:a", "pcm_s16le", str(out_path),
        ])
        return out_path

    inputs, labels = [], []
    for i, off in enumerate(offsets):
        ms = max(0, int(off * 1000))
        seg = (
            f"anoisesrc=color=white:amplitude=0.65:duration=0.5,"
            f"bandpass=f=1800:width_type=h:w=2600,"
            f"afade=t=in:st=0:d=0.08,afade=t=out:st=0.18:d=0.32,"
            f"adelay={ms}"
        )
        inputs += ["-f", "lavfi", "-i", seg]
        labels.append(f"[{i}:a]")
    filter_str = (
        "".join(labels) + f"amix=inputs={len(offsets)}:duration=longest:normalize=0,"
        f"volume=0.45,apad,atrim=0:{total_duration}[out]"
    )
    run([
        "ffmpeg", "-y", *inputs, "-filter_complex", filter_str, "-map", "[out]",
        "-ac", "2", "-c:a", "pcm_s16le", str(out_path),
    ])
    return out_path


def build_subbass(duration: float, work_dir: Path) -> Path:
    out_path = work_dir / "subbass.wav"
    d = duration + 0.5
    filt = (
        f"sine=frequency=46:duration={d},lowpass=f=110,"
        f"tremolo=f=0.11:d=0.3,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={max(d-2,0)}:d=2,"
        f"volume=0.14"
    )
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", filt, "-t", str(duration), "-ac", "2", "-c:a", "pcm_s16le", str(out_path)])
    return out_path


def layer_soundscape(base_audio: Path, shots, cfg: Config, duration: float, work_dir: Path) -> Path:
    xfade = cfg.transition_duration
    durations = [s.duration for s in shots]
    offsets = _transition_offsets(durations, xfade)

    print("  layering ambience (water/outdoor/room-tone), cut whooshes, sub-bass ...")
    ambience = build_ambience_bed(shots, xfade, work_dir)
    whoosh = build_whoosh_track(offsets, duration, work_dir)
    subbass = build_subbass(duration, work_dir)

    out_path = work_dir / "soundtrack.m4a"
    run([
        "ffmpeg", "-y",
        "-i", str(base_audio), "-i", str(ambience), "-i", str(whoosh), "-i", str(subbass),
        "-filter_complex",
        "[0:a]aformat=channel_layouts=stereo[a0];"
        "[1:a]aformat=channel_layouts=stereo[a1];"
        "[2:a]aformat=channel_layouts=stereo[a2];"
        "[3:a]aformat=channel_layouts=stereo[a3];"
        "[a0][a1][a2][a3]amix=inputs=4:duration=first:normalize=0,"
        f"afade=t=in:st=0:d=1.0,afade=t=out:st={max(duration-1.2,0)}:d=1.2[mixed]",
        "-map", "[mixed]", "-t", str(duration),
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ])
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
