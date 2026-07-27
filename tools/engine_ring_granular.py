"""Granular reassembly of the real engine cuts -- real cards, shuffled deck.

The one family the synthesis arc never tried (and the only one that puts
zero synthetic noise in the cab): slice the approved real cut into
revolution-synchronous grains and reassemble them in a shuffled,
never-repeating order over a much longer loop. Every millisecond is the
real truck; only the ORDER is new. The owner's "three shudders" WERE the
cut's envelope sequence -- reordering its pieces destroys the pattern
itself rather than masking it.

Mechanics:
- Grains are GRAIN_REVS whole revolutions, cut at revolution boundaries
  (rev period from the comb search), so every grain starts and ends at
  the same crank phase: any grain can follow any other with the
  combustion rhythm intact.
- Sequencing is a shuffle-bag (no grain twice in a row, whole deck dealt
  before reshuffle -- the play_bank discipline).
- Joins are short linear crossfades (phase-aligned material) at rev
  boundaries; the final loop is wrap-spliced tail-into-head.
- Output ~TARGET_S per band, WAV, installed to the ff-audio overlay ONLY.
  Mirrors keep the shipped repaired originals until the owner's ear
  rules. The known risk to listen for: recognizing INDIVIDUAL grains
  ("that little cough again") -- the vocabulary from a ~2 s cut is
  15-25 grains.

Usage: uv run python tools/engine_ring_granular.py
"""

from __future__ import annotations

import importlib.util
import os
import random

import numpy as np
import soundfile as sf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUND0 = os.path.join(REPO, "sound-source", "ring-round0")
LICENSED_ENGINE = os.path.join(
    REPO, "src", "freight_fate", "assets", "sounds-licensed", "engine"
)
STAGE_DIR = r"C:\temp\ffsound\granular"

BANDS = (
    ("low", 950.0),
    ("mid", 1150.0),
    ("midhigh", 1425.0),
    ("high", 1900.0),
)

GRAIN_REVS = 2  # grain length in whole revolutions
HOP_REVS = 1  # grain start spacing in the source (overlapping vocabulary)
TARGET_S = 18.0  # output loop length before wrap splice
JOIN_FADE_S = 0.008  # linear crossfade at each grain join
SPLICE_S = 0.025  # final wrap splice
SEED = 0x4752414E  # "GRAN"


def _pulse_module():
    spec = importlib.util.spec_from_file_location(
        "ringpulse", os.path.join(REPO, "tools", "engine_ring_pulse.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ShuffleBag:
    def __init__(self, count: int, rng: random.Random) -> None:
        self._count = count
        self._rng = rng
        self._bag: list[int] = []
        self._last = -1

    def draw(self) -> int:
        if not self._bag:
            self._bag = list(range(self._count))
            self._rng.shuffle(self._bag)
            if len(self._bag) > 1 and self._bag[-1] == self._last:
                self._bag[0], self._bag[-1] = self._bag[-1], self._bag[0]
        self._last = self._bag.pop()
        return self._last


def reassemble(band: str, native_rpm: float, refine) -> None:
    src_path = os.path.join(ROUND0, f"{band}_original.wav")
    x, sr = sf.read(src_path, dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = len(x)
    spec_mag = np.abs(np.fft.rfft(x * np.hanning(n)))
    rev_hz = refine(spec_mag, sr, n, native_rpm / 60.0)
    rev_len = sr / rev_hz  # samples per revolution (fractional)

    grain_len = int(round(GRAIN_REVS * rev_len))
    hop = int(round(HOP_REVS * rev_len))
    starts = list(range(0, n - grain_len, hop))
    grains = [x[s : s + grain_len] for s in starts]
    if len(grains) < 4:
        print(f"{band}: only {len(grains)} grains, skipped")
        return

    rng = random.Random(SEED + hash(band) % 1000)
    bag = ShuffleBag(len(grains), rng)
    fade = int(JOIN_FADE_S * sr)
    ramp = np.linspace(0.0, 1.0, fade)
    target = int(TARGET_S * sr)
    out = np.zeros(target + grain_len)
    pos = 0
    first = True
    while pos + grain_len < len(out):
        g = grains[bag.draw()].copy()
        if first:
            out[:grain_len] = g
            pos = grain_len - fade
            first = False
            continue
        # linear crossfade into the join (phase-aligned at rev boundaries)
        out[pos : pos + fade] = out[pos : pos + fade] * (1.0 - ramp) + g[:fade] * ramp
        out[pos + fade : pos + grain_len] = g[fade:]
        pos += grain_len - fade
    out = out[:pos]
    # final wrap splice: tail crossfades into the head's material
    w = int(SPLICE_S * sr)
    head = out[:w].copy()
    out = out[w:].copy()
    ramp_w = np.linspace(0.0, 1.0, w)
    out[-w:] = out[-w:] * (1.0 - ramp_w) + head * ramp_w
    out *= np.sqrt(np.mean(x**2) / (np.mean(out**2) + 1e-12))
    peak = np.max(np.abs(out))
    if peak > 0.97:
        out = out / peak * 0.97

    os.makedirs(STAGE_DIR, exist_ok=True)
    sf.write(os.path.join(STAGE_DIR, f"{band}_granular.wav"), out.astype(np.float32), sr)
    sf.write(
        os.path.join(LICENSED_ENGINE, f"{band}.wav"),
        out.astype(np.float32),
        sr,
        subtype="PCM_16",
    )
    print(
        f"{band:8s} rev {rev_hz:5.2f} Hz  {len(grains)} grains x {GRAIN_REVS} revs  "
        f"-> {len(out)/sr:5.2f}s  installed (ff-audio overlay only) + staged"
    )


def main() -> None:
    mod = _pulse_module()
    for band, native in BANDS:
        reassemble(band, native, mod.refine_rev_hz)
    print("\nMirrors untouched: the shipped repaired originals stay until the ear rules.")


if __name__ == "__main__":
    main()
