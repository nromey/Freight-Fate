"""Ring rebuild ship recipe (owner-converged, 2026-07-27).

The ear walked the whole space and landed here: each driving band is the
REAL approved cut, tiled to ~5 s, at 75 percent -- with the firing-
modulated comb-boosted synthesis underneath as camouflage for the tile
repetition. The bed (engine_ring_pulse at FORCE_MOD 0.3, HARMONIC_GAIN
1.7) never repeats, so the ear cannot lock onto the tiled layer's period;
the real layer keeps the voice unmistakably the truck.

Ear ledger that produced these numbers:
- pure resynthesis = jet (stationary noise phase); pulse train = popcorn
  (kurtosis 49 vs the cab's ~0); deep modulation = raspberry;
- real share 80-90 = "shaky" (the cut's own envelope surge re-emerging);
  75 = the sweet spot;
- plain bed under 75 = faint turboprop; comb 1.7x bed = the pick.

Renders all four bands, installs into the ff-audio licensed overlay, and
stages copies. MIRRORING (main worktree + Dropbox) stays a manual step
after the owner's in-game confirmation lap -- rounds are one-way in the
mirrors.

Usage: uv run python tools/engine_ring_blend.py
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import soundfile as sf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUND0 = os.path.join(REPO, "sound-source", "ring-round0")
LICENSED_ENGINE = os.path.join(
    REPO, "src", "freight_fate", "assets", "sounds-licensed", "engine"
)
STAGE_DIR = r"C:\temp\ffsound\round2\final"

REAL_SHARE = 0.75  # owner: 80-90 goes shaky, 75 is the sweet spot
BED_MOD = 0.3  # deeper reads as a raspberry
BED_COMB = 1.7  # the pvfp lesson: a prouder comb, less turboprop wash
SPLICE_S = 0.025  # the tiled real layer is cut mid-tile: wrap-splice the mix

BANDS = (
    ("low", 950.0),
    ("mid", 1150.0),
    ("midhigh", 1425.0),
    ("high", 1900.0),
)


def _pulse_module():
    spec = importlib.util.spec_from_file_location(
        "ringpulse", os.path.join(REPO, "tools", "engine_ring_pulse.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    mod = _pulse_module()
    mod.FORCE_MOD = BED_MOD
    mod.HARMONIC_GAIN = BED_COMB
    os.makedirs(STAGE_DIR, exist_ok=True)
    g_real = REAL_SHARE
    g_synth = float(np.sqrt(1.0 - g_real**2))
    for index, (band, native) in enumerate(BANDS):
        mod.synthesize(band, native, index)  # writes the bed to the overlay
        bed, sr = sf.read(
            os.path.join(LICENSED_ENGINE, f"{band}.wav"), dtype="float64"
        )
        real, sr2 = sf.read(
            os.path.join(ROUND0, f"{band}_original.wav"), dtype="float64"
        )
        assert sr == sr2
        tiled = np.tile(real, int(np.ceil(len(bed) / len(real))))[: len(bed)]
        out = tiled * g_real + bed * g_synth
        # The tiled layer is cut mid-tile at the loop end: classic wrap
        # splice (tail crossfades into the head's preceding material,
        # linear ramp -- correlated near-periodic ends), as fix_loop_seams.
        w = int(SPLICE_S * sr)
        head = out[:w].copy()
        out = out[w:].copy()
        ramp = np.linspace(0.0, 1.0, w)
        out[-w:] = out[-w:] * (1.0 - ramp) + head * ramp
        out *= np.sqrt(np.mean(real**2) / (np.mean(out**2) + 1e-12))
        peak = np.max(np.abs(out))
        if peak > 0.97:
            out = out / peak * 0.97
        sf.write(
            os.path.join(LICENSED_ENGINE, f"{band}.wav"),
            out.astype(np.float32),
            sr,
            subtype="PCM_16",
        )
        sf.write(
            os.path.join(STAGE_DIR, f"{band}_final.wav"), out.astype(np.float32), sr
        )
        print(f"{band:8s} real {g_real:.0%} over comb-{BED_COMB:.1f} bed -> installed + staged")
    print("\nInstalled to the ff-audio overlay ONLY. Mirror after the owner's lap.")


if __name__ == "__main__":
    main()
