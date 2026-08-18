"""Storyboard: turns analyzed assets into an ordered, editable shot list.

Written to output/storyboard.json after every fresh run so the choices are
inspectable and hand-tunable — re-run with --storyboard to render the edited
version without repeating analysis/selection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
from PIL import Image

from .analysis import Asset, NARRATIVE_ORDER
from .config import Config

# Camera-move presets used for still photos. Selection logic lives in
# choose_motion() below; every preset is a pure affine crop/zoom/pan of the
# original pixels, so none of them can invent or warp geometry.
MOTION_PUSH_IN = "push_in"
MOTION_PULL_BACK = "pull_back"
MOTION_SLOW_PAN = "slow_pan"
MOTION_HOLD_DRIFT = "hold_drift"


@dataclass
class Shot:
    path: str
    kind: str                 # "image" | "video"
    category: str
    duration: float
    motion: str = MOTION_PUSH_IN
    sky_parallax: bool = False
    focal_x: float = 0.5      # fraction of width, focal point for push/pull
    focal_y: float = 0.5
    quality: float = 0.0
    caption: str = ""         # optional amenity callout shown during this shot


def _focal_point(path: Path) -> tuple[float, float]:
    """Weighted centroid of gradient energy, biased toward the central 80%
    of the frame so edge clutter doesn't drag the virtual camera off-center."""
    with Image.open(path) as im:
        g = np.array(im.convert("L").resize((160, 160)), dtype=np.float32)
    gy, gx = np.gradient(g)
    energy = np.sqrt(gx**2 + gy**2)
    h, w = energy.shape
    margin_y, margin_x = int(h * 0.1), int(w * 0.1)
    mask = np.zeros_like(energy)
    mask[margin_y : h - margin_y, margin_x : w - margin_x] = 1
    energy = energy * mask
    total = energy.sum()
    if total < 1e-6:
        return 0.5, 0.5
    ys, xs = np.indices(energy.shape)
    fx = float((xs * energy).sum() / total / w)
    fy = float((ys * energy).sum() / total / h)
    # keep the focal point away from the extreme edges so zoom crops stay valid
    fx = float(np.clip(fx, 0.3, 0.7))
    fy = float(np.clip(fy, 0.3, 0.7))
    return fx, fy


def _symmetry_score(path: Path) -> float:
    """0..1, how bilaterally symmetric the frame is (facades, symmetric
    interiors). High symmetry -> prefer a minimal, respectful camera move."""
    with Image.open(path) as im:
        g = np.array(im.convert("L").resize((160, 160)), dtype=np.float32)
    flipped = np.fliplr(g)
    diff = np.abs(g - flipped).mean()
    return float(np.clip(1.0 - diff / 60.0, 0.0, 1.0))


def choose_motion(asset: Asset, cfg: Config) -> tuple[str, bool, float, float]:
    fx, fy = _focal_point(asset.path)
    sym = _symmetry_score(asset.path)

    if asset.category == "Exterior" and sym > 0.55:
        return MOTION_HOLD_DRIFT, False, 0.5, fy

    sky_parallax = cfg.sky_parallax and asset.outdoor_conf > 0.35
    if asset.category in ("Exterior", "View", "Pool", "Garden", "Golden Hour"):
        motion = MOTION_SLOW_PAN if fx < 0.45 or fx > 0.55 else MOTION_PUSH_IN
        return motion, sky_parallax, fx, fy

    # interiors: draw the eye toward the strongest focal point, alternate
    # push/pull for variety across a run of similar rooms
    motion = MOTION_PUSH_IN if asset.quality >= 0 else MOTION_PULL_BACK
    return motion, False, fx, fy


def _dedupe_by_category(assets: list[Asset], max_shots: int) -> list[Asset]:
    """Keep the best asset per category first (avoid two kitchens eating the
    runway), then fill remaining slots with the next-best leftovers."""
    by_cat: dict[str, list[Asset]] = {}
    for a in assets:
        by_cat.setdefault(a.category, []).append(a)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda a: a.quality, reverse=True)

    primary = [lst[0] for lst in by_cat.values()]
    primary.sort(key=lambda a: a.quality, reverse=True)

    leftovers = sorted(
        (a for lst in by_cat.values() for a in lst[1:]),
        key=lambda a: a.quality, reverse=True,
    )

    selected = primary[:max_shots]
    if len(selected) < max_shots:
        selected += leftovers[: max_shots - len(selected)]
    return selected


def _adaptive_image_duration(selected: list[Asset], cfg: Config) -> float:
    """Solve per-image shot duration so the assembled runtime lands near the
    middle of the 20-30s target, regardless of how many shots were selected
    (a fixed per-shot duration either drags a 5-shot cut under 20s or pushes
    a 9-shot cut past 30s)."""
    from .config import TARGET_TOTAL
    target = sum(TARGET_TOTAL) / 2
    xfade = cfg.transition_duration
    fixed_sum = sum(a.duration for a in selected if a.kind == "video" and 1.5 <= a.duration <= 6.0)
    n_image = sum(1 for a in selected if not (a.kind == "video" and 1.5 <= a.duration <= 6.0))
    if n_image == 0:
        return cfg.shot_duration
    needed = (target - fixed_sum + (len(selected) - 1) * xfade) / n_image
    return float(np.clip(needed, 2.6, 6.0))


def build_storyboard(assets: list[Asset], cfg: Config) -> list[Shot]:
    keep_n = max(min(len(assets), cfg.max_shots), min(5, len(assets)))
    selected = _dedupe_by_category(assets, keep_n)

    def narrative_key(a: Asset):
        try:
            return NARRATIVE_ORDER.index(a.category)
        except ValueError:
            return len(NARRATIVE_ORDER)

    selected.sort(key=narrative_key)
    image_duration = _adaptive_image_duration(selected, cfg)

    shots: list[Shot] = []
    for a in selected:
        dur = a.duration if a.kind == "video" and 1.5 <= a.duration <= 6.0 else image_duration
        if a.kind == "image":
            motion, sky_px, fx, fy = choose_motion(a, cfg)
        else:
            motion, sky_px, fx, fy = "video", False, 0.5, 0.5
        shots.append(Shot(
            path=str(a.path), kind=a.kind, category=a.category,
            duration=round(dur, 2), motion=motion, sky_parallax=sky_px,
            focal_x=fx, focal_y=fy, quality=round(a.quality, 3),
        ))

    _assign_captions(shots, cfg)
    return shots


def _assign_captions(shots: list[Shot], cfg: Config) -> None:
    """One combined amenity line, shown once — not a callout per shot.
    Placed on the strongest outdoor/amenity shot available (pool, then
    view/garden), falling back to the middle shot, so it never collides
    with the opening title card or the closing CTA."""
    if not cfg.amenities or len(shots) < 2:
        return
    line = " • ".join(cfg.amenities)
    candidates = [i for i, s in enumerate(shots) if 0 < i < len(shots) - 1 and s.category == "Pool"]
    if not candidates:
        candidates = [i for i, s in enumerate(shots) if 0 < i < len(shots) - 1 and s.category in ("View", "Garden")]
    if not candidates:
        candidates = list(range(1, len(shots) - 1)) or [0]
    shots[candidates[0]].caption = line


def write_storyboard(shots: list[Shot], cfg: Config, path: Path) -> None:
    data = {
        "property_name": cfg.property_name,
        "location": cfg.location,
        "amenities": cfg.amenities,
        "cta": cfg.cta,
        "shots": [asdict(s) for s in shots],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_storyboard(path: Path) -> tuple[list[Shot], dict]:
    data = json.loads(path.read_text())
    shots = [Shot(**sh) for sh in data["shots"]]
    return shots, data
