"""Harvest revolution-synchronous grains from a long engine take -- 60624.

The 176 s Splice take SemiTruckEngine_BW.60624 (licensed, Large Vehicles
pack -- the NEWER, smoother truck; the owner finds the 896 Mack's rattle
too grain-recognizable) holds ~950 / ~1100 / ~1685 rpm steadily and
sweeps between them. Unlike the loop pipeline, granular assembly does
not need steady holds: ANY two-revolution window whose LOCAL rev period
matches a target band (within GRAIN_TOL) donates a grain, so the sweeps
fill the 1100-1685 gap.

Per target band: track the local rev period over the whole take (comb
search per window, round-5 rules -- never the spectral argmax), collect
every non-overlapping 2-rev window within tolerance of the band's
native, then shuffle-assemble an 18 s loop exactly as
engine_ring_granular does (rev-boundary joins, linear fades, wrap
splice).

Writes staged band wavs to C:\\temp\\ffsound\\granular60624 and prints
deck sizes. It does NOT install: the 60624 ring needs retuned natives
(a code change) and the owner's voice-level sign-off first.

Usage: uv run python tools/engine_grain_harvest.py
"""

from __future__ import annotations

import os
import random

import numpy as np
import soundfile as sf

SOURCE = r"C:\temp\ffsound\Splice\Samples\packs\Large Vehicles\SemiTruckEngine_BW.60624.wav"
STAGE_DIR = r"C:\temp\ffsound\granular60624"
OUT_SR = 44100

# Retuned native table for this truck's actual states; the 1400 band is
# fed by sweep material. Idle: the take's floor is ~950 -- whether the
# game idle keeps the 896 idle (two-truck seam at the idle/low window)
# is an OPEN question for the owner's ear.
TARGETS = (
    ("low", 950.0),
    ("mid", 1100.0),
    ("midhigh", 1400.0),
    ("high", 1685.0),
)

GRAIN_REVS = 2
GRAIN_TOL = 0.02  # local rev period within 2 percent of the band target
TRACK_WIN_S = 0.35
TRACK_HOP_S = 0.1
TARGET_S = 18.0
JOIN_FADE_S = 0.008
SPLICE_S = 0.025
RMS_FLOOR_FRAC = 0.4  # reject grains quieter than this fraction of band median
# Deck hygiene (owner round: "brake hisses in there" + "kind of juttery").
# The takes carry air events, and grains harvested minutes apart differ in
# level and color -- a clean deck must be a CLUSTER, not a census.
HISS_CULL_RATIO = 1.6  # reject grains whose 3-8 kHz share exceeds median x this
RMS_CULL_DB = 2.0  # reject grains outside median +/- this many dB
GAIN_EVEN_FRAC = 0.5  # pull survivors' gains this fraction toward the median
SEED = 0x36303632  # "6062"


def load_source() -> tuple[np.ndarray, int]:
    x, sr = sf.read(SOURCE, dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != OUT_SR:
        from scipy.signal import resample_poly
        from fractions import Fraction

        fr = Fraction(OUT_SR, sr).limit_denominator(1000)
        x = resample_poly(x, fr.numerator, fr.denominator)
        sr = OUT_SR
    return x, sr


def rev_track(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Local revolution rate (Hz) and RMS at TRACK_HOP_S spacing."""
    win = int(TRACK_WIN_S * sr)
    hop = int(TRACK_HOP_S * sr)
    times, revs, rmss = [], [], []
    hann = np.hanning(win)
    for start in range(0, len(x) - win, hop):
        frame = x[start : start + win]
        spec = np.abs(np.fft.rfft(frame * hann))
        best = (0.0, 0.0)
        for cand in np.arange(8.0, 36.0, 0.15):
            score = 0.0
            for k in range(1, 19):
                b = int(round(k * cand * win / sr))
                if b >= len(spec):
                    break
                score += (2.0 if k % 3 == 0 else 0.6) * spec[b]
            if score > best[0]:
                best = (score, cand)
        times.append(start)
        revs.append(best[1])
        rmss.append(float(np.sqrt(np.mean(frame**2))))
    return np.array(times), np.array(revs), np.array(rmss)


def harvest(x, sr, times, revs, rmss, target_rev_hz: float) -> list[np.ndarray]:
    ok = np.abs(revs - target_rev_hz) / target_rev_hz < GRAIN_TOL
    med_rms = np.median(rmss[ok]) if ok.any() else 0.0
    grains: list[np.ndarray] = []
    pos = 0
    for i in range(len(times)):
        if not ok[i] or rmss[i] < RMS_FLOOR_FRAC * med_rms:
            continue
        start = int(times[i])
        if start < pos:
            continue  # non-overlapping harvest
        # local grain length from the LOCAL period, so sweeps stay in tune
        grain_len = int(round(GRAIN_REVS * sr / revs[i]))
        if start + grain_len > len(x):
            break
        g = x[start : start + grain_len]
        # normalize each grain's playback length to the band target by rate:
        # a 2 percent stretch is inaudible and keeps every join phase-true
        target_len = int(round(GRAIN_REVS * sr / target_rev_hz))
        idx = np.linspace(0, len(g) - 1, target_len)
        i0 = idx.astype(int)
        i1 = np.minimum(i0 + 1, len(g) - 1)
        frac = idx - i0
        grains.append(g[i0] * (1 - frac) + g[i1] * frac)
        pos = start + grain_len
    return _clean_deck(grains, sr)


def _clean_deck(grains: list[np.ndarray], sr: int) -> list[np.ndarray]:
    """Cull hissy and off-level grains; even out the survivors' gains."""
    if len(grains) < 8:
        return grains
    def hiss_share(g: np.ndarray) -> float:
        spec = np.abs(np.fft.rfft(g)) ** 2
        freqs = np.fft.rfftfreq(len(g), 1.0 / sr)
        hi = spec[(freqs >= 3000) & (freqs <= 8000)].sum()
        return float(hi / (spec.sum() + 1e-18))
    rms = np.array([np.sqrt(np.mean(g**2)) for g in grains])
    hiss = np.array([hiss_share(g) for g in grains])
    rms_med = np.median(rms)
    hiss_med = np.median(hiss)
    db = 20.0 * np.log10(rms / (rms_med + 1e-18))
    keep = (np.abs(db) <= RMS_CULL_DB) & (hiss <= hiss_med * HISS_CULL_RATIO)
    survivors = [g for g, k in zip(grains, keep) if k]
    if len(survivors) < 8:  # too aggressive for a thin deck: relax to hiss-only
        survivors = [g for g, h in zip(grains, hiss) if h <= hiss_med * HISS_CULL_RATIO]
    kept_rms = np.median([np.sqrt(np.mean(g**2)) for g in survivors])
    out = []
    for g in survivors:
        r = np.sqrt(np.mean(g**2)) + 1e-18
        out.append(g * (1.0 + GAIN_EVEN_FRAC * (kept_rms / r - 1.0)))
    return out


def assemble(grains: list[np.ndarray], sr: int, rng: random.Random) -> np.ndarray:
    fade = int(JOIN_FADE_S * sr)
    ramp = np.linspace(0.0, 1.0, fade)
    target = int(TARGET_S * sr)
    grain_len = len(grains[0])
    out = np.zeros(target + grain_len)
    bag: list[int] = []
    last = -1
    pos = 0
    first = True
    while pos + grain_len < len(out):
        if not bag:
            bag = list(range(len(grains)))
            rng.shuffle(bag)
            if len(bag) > 1 and bag[-1] == last:
                bag[0], bag[-1] = bag[-1], bag[0]
        last = bag.pop()
        g = grains[last]
        if first:
            out[:grain_len] = g
            pos = grain_len - fade
            first = False
            continue
        out[pos : pos + fade] = out[pos : pos + fade] * (1.0 - ramp) + g[:fade] * ramp
        out[pos + fade : pos + grain_len] = g[fade:]
        pos += grain_len - fade
    out = out[:pos]
    w = int(SPLICE_S * sr)
    head = out[:w].copy()
    out = out[w:].copy()
    ramp_w = np.linspace(0.0, 1.0, w)
    out[-w:] = out[-w:] * (1.0 - ramp_w) + head * ramp_w
    peak = np.max(np.abs(out))
    return out / peak * 0.85 if peak > 0.85 else out


def main() -> None:
    os.makedirs(STAGE_DIR, exist_ok=True)
    print("loading + resampling the take...")
    x, sr = load_source()
    print("tracking revolution rate over the take...")
    times, revs, rmss = rev_track(x, sr)
    rpm = revs * 60.0
    print(
        f"take coverage: {np.percentile(rpm, 2):.0f}-{np.percentile(rpm, 98):.0f} rpm "
        f"(min {rpm.min():.0f})"
    )
    for band, native in TARGETS:
        target_rev = native / 60.0
        grains = harvest(x, sr, times, revs, rmss, target_rev)
        if len(grains) < 8:
            print(f"{band:8s} ~{native:.0f} rpm: only {len(grains)} grains -- SKIPPED")
            continue
        rng = random.Random(SEED + int(native))
        out = assemble(grains, sr, rng)
        sf.write(
            os.path.join(STAGE_DIR, f"{band}_60624.wav"), out.astype(np.float32), sr
        )
        print(f"{band:8s} ~{native:.0f} rpm: {len(grains)} grains -> {len(out)/sr:.1f}s staged")
    print("\nStaged only -- no install. Retuned natives + owner sign-off first.")


if __name__ == "__main__":
    main()
