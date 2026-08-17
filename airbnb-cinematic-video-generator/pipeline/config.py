"""Configuration for the cinematic reel pipeline.

Everything a client-facing render needs to be tuned per property lives here:
text content, pacing, and the color-grade/parallax intensity knobs. Defaults
are tuned toward restraint (luxury real-estate, not a TikTok template).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

WIDTH, HEIGHT = 1080, 1920
FPS = 30

# Target on-screen time per shot and overall runtime band.
MIN_SHOTS, MAX_SHOTS = 5, 9
SHOT_DURATION = 3.4
TARGET_TOTAL = (20, 30)  # seconds


@dataclass
class Config:
    # --- text content (kept sparse on purpose) ---
    property_name: str = ""
    location: str = ""
    amenities: list[str] = field(default_factory=list)   # e.g. ["PRIVATE POOL", "OCEAN VIEW", "5 BEDROOMS"]
    cta: str = "BOOK YOUR STAY"

    # --- paths ---
    input_dir: str = "input"
    music_dir: str = "music"
    output_dir: str = "output"

    # --- pacing / style ---
    shot_duration: float = SHOT_DURATION
    max_shots: int = MAX_SHOTS
    transition: str = "fade"          # restrained crossfade only, by design
    transition_duration: float = 0.7

    # --- color grade intensity (0 = off, 1 = default, >1 = stronger) ---
    grade_strength: float = 1.0
    film_grain: bool = True

    # --- motion ---
    sky_parallax: bool = True         # allow the safe two-layer sky parallax
    max_zoom: float = 1.12            # ceiling on push-in amount; keeps moves subtle

    # --- audio ---
    music_volume: float = 0.35

    def __post_init__(self):
        if isinstance(self.amenities, str):
            self.amenities = [a.strip() for a in self.amenities.split(",") if a.strip()]

    @classmethod
    def load(cls, path: str | Path | None) -> "Config":
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        data = json.loads(p.read_text())
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)
