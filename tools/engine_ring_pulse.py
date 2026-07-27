"""Ring rebuild round 2: firing-modulated resynthesis -- growl, not hiss.

Round 1 (engine_ring_extend.py) preserved each band's spectrum but
rebuilt everything between the harmonic lines as STATIONARY random-phase
noise, and the owner heard exactly that: a jet, not a truck. Measurement
agreed once we knew where to look: the real cut's broadband bed BREATHES
at the firing rate (roughness index ~0.1 at 3 x rev rate); stationary
noise with the same spectrum does not breathe at all. (A pure pulse-train
rebuild overshot the other way -- kurtosis 49 vs the cut's ~0: the cab
smooths firings into swells, so the truth is modulated noise, not clicks.)

This round keeps what each attempt proved out:

- The harmonic skeleton from round 1 (partials at revolution-rate
  harmonics, original amplitudes AND phases, exact circular frequencies,
  slow per-octave wander) -- it was never the problem.
- Fresh random-phase noise shaped by the residual PSD -- exact timbre by
  construction, no repeating envelope.
- NEW: the noise is amplitude-modulated by a jittered per-cylinder firing
  wave (fixed cylinder spread = the lope; per-event amplitude/timing
  jitter = shot noise), with the modulation depth FITTED per band so the
  synthesized roughness index lands on the approved cut's. Multiplicative
  roughness leaves the PSD intact where convolutional smearing rolled off
  everything above 1 kHz.

Output is circular by construction. Candidates are STAGED -- written to
the staging dir and the ff-audio overlay only; no mirroring anywhere
until the owner's ear signs off (rounds are one-way in the mirrors).

Usage: uv run python tools/engine_ring_pulse.py
"""

from __future__ import annotations

import os

import numpy as np
import soundfile as sf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUND0 = os.path.join(REPO, "sound-source", "ring-round0")
LICENSED_ENGINE = os.path.join(
    REPO, "src", "freight_fate", "assets", "sounds-licensed", "engine"
)
STAGE_DIR = r"C:\temp\ffsound\round2"

BANDS = (
    ("low", 950.0),
    ("mid", 1150.0),
    ("midhigh", 1425.0),
    ("high", 1900.0),
)

TARGET_S = 5.0
FIRINGS_PER_REV = 3  # inline-six, four-stroke
CYL_SPREAD = (0.08, -0.05, -0.02)  # fixed per-rev firing strengths: the lope
AMP_JITTER = 0.07  # per-event amplitude sigma (owner: heavy jitter = raspberry spit)
TIME_JITTER = 0.015  # per-event timing sigma, fraction of the firing period
SWELL_WIDTH = 1.2  # firing swell width, x firing period (cab-smoothed whump)
MOD_DEPTHS = (0.0, 0.3, 0.5, 0.8, 1.2, 1.8)  # candidates for the roughness fit
# The roughness fit collapsed to 0.0 on every band -- the metric cannot
# separate the truck from the jet (the harmonic comb's own beating
# dominates the envelope in both). FORCE_MOD bypasses the fit with the
# physical hypothesis instead: noise bursts phase-locked to the firing
# comb, which is what a cylinder event actually does. The owner's ear is
# the only instrument that can grade this. Ear ledger: 0.8 = "blowing a
# raspberry at different speeds" (too deep, too sputtery -- jitter was
# also halved on that verdict); the smooth stationary bed IS the cab
# wash, so the depth rides ON it, quietly.
FORCE_MOD: float | None = 0.3
MAX_PARTIAL_HZ = 9000.0
PARTIAL_SEARCH_BINS = 2
WANDER_DEPTH = 0.10
WANDER_MAX_HZ = 2.5
SEED = 0x5254524B  # "RTRK"


def refine_rev_hz(mag: np.ndarray, sr: int, n: int, nominal: float) -> float:
    best = (0.0, nominal)
    for cand in np.linspace(nominal * 0.94, nominal * 1.06, 121):
        ks = np.arange(3, 31, 3)
        bins = np.round(ks * cand * n / sr).astype(int)
        bins = bins[bins < len(mag)]
        score = float(np.sum(mag[bins]))
        if score > best[0]:
            best = (score, float(cand))
    return best[1]


def circular_wander(rng: np.random.Generator, length: int, sr: int) -> np.ndarray:
    spec = np.zeros(length // 2 + 1, dtype=complex)
    max_bin = max(2, int(WANDER_MAX_HZ * length / sr))
    spec[1:max_bin] = rng.random(max_bin - 1) * np.exp(
        1j * rng.uniform(0.0, 2.0 * np.pi, max_bin - 1)
    )
    w = np.fft.irfft(spec, length)
    return w / (np.max(np.abs(w)) + 1e-12)


def roughness_index(x: np.ndarray, sr: int, f_fire: float) -> float:
    """Firing-rate modulation share of the 300-5000 Hz bed's envelope.

    THE truck-vs-jet metric: the real cut's broadband energy breathes at
    the firing rate; stationary noise with the same spectrum does not.
    """
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    band = (freqs >= 300) & (freqs <= 5000)
    y = np.fft.irfft(np.where(band, spec, 0.0), len(x))
    frame = max(1, int(sr / 1000.0))
    m = len(y) // frame
    env = np.sqrt(np.mean(y[: m * frame].reshape(m, frame) ** 2, axis=1))
    env = env - np.mean(env)
    espec = np.abs(np.fft.rfft(env * np.hanning(len(env))))
    efreqs = np.fft.rfftfreq(len(env), frame / sr)
    peak = (efreqs >= f_fire * 0.85) & (efreqs <= f_fire * 1.15)
    total = float(np.sum(espec[(efreqs >= 5) & (efreqs <= 200)])) + 1e-12
    return float(np.sum(espec[peak])) / total


def firing_wave(
    rng: np.random.Generator, out_len: int, revs: int, sr: int
) -> np.ndarray:
    """Zero-mean, unit-std firing modulation wave: jittered per-cylinder
    swells at the firing rate, circular by construction."""
    rev_period = out_len / revs
    firing_period = rev_period / FIRINGS_PER_REV
    train = np.zeros(out_len)
    for r in range(revs):
        for c in range(FIRINGS_PER_REV):
            base = r * rev_period + c * firing_period
            pos = base + rng.normal(0.0, TIME_JITTER) * firing_period
            amp = (1.0 + CYL_SPREAD[c]) * (1.0 + rng.normal(0.0, AMP_JITTER))
            idx = int(np.floor(pos)) % out_len
            frac = pos - np.floor(pos)
            train[idx] += amp * (1.0 - frac)
            train[(idx + 1) % out_len] += amp * frac
    klen = max(3, int(SWELL_WIDTH * firing_period))
    kernel = np.fft.rfft(np.hanning(klen), out_len)
    wave = np.fft.irfft(np.fft.rfft(train) * kernel, out_len)
    wave = wave - np.mean(wave)
    return wave / (np.std(wave) + 1e-12)


def synthesize(band: str, native_rpm: float, index: int) -> None:
    src_path = os.path.join(ROUND0, f"{band}_original.wav")
    x, sr = sf.read(src_path, dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = len(x)
    window = np.hanning(n)
    spec = np.fft.rfft(x * window)
    spec_mag = np.abs(spec)
    src_freqs = np.fft.rfftfreq(n, 1.0 / sr)

    rev_hz = refine_rev_hz(spec_mag, sr, n, native_rpm / 60.0)
    f_fire = rev_hz * FIRINGS_PER_REV
    revs = max(8, round(TARGET_S * rev_hz))
    out_len = int(round(revs / rev_hz * sr))
    rev_hz_exact = revs * sr / out_len

    rng = np.random.default_rng(SEED + index)
    t = np.arange(out_len) / sr

    # -- harmonic skeleton (round-1 recipe: it was never the problem) ---------
    harmonic = np.zeros(out_len)
    harmonic_energy = 0.0
    noise_spec_mag = spec_mag.copy()
    k_max = int(MAX_PARTIAL_HZ / rev_hz)
    groups: dict[int, np.ndarray] = {}
    for k in range(1, k_max + 1):
        center = int(round(k * rev_hz * n / sr))
        lo = max(1, center - PARTIAL_SEARCH_BINS)
        hi = min(len(spec) - 1, center + PARTIAL_SEARCH_BINS + 1)
        if hi <= lo:
            continue
        peak_bin = lo + int(np.argmax(spec_mag[lo:hi]))
        nb_lo, nb_hi = max(1, peak_bin - 12), min(len(spec) - 1, peak_bin + 13)
        floor = np.median(spec_mag[nb_lo:nb_hi]) + 1e-12
        if spec_mag[peak_bin] < 3.0 * floor:
            continue
        amp = 2.0 * spec_mag[peak_bin] / np.sum(window)
        phase = np.angle(spec[peak_bin])
        octave = int(np.log2(max(1, k)))
        if octave not in groups:
            groups[octave] = circular_wander(rng, out_len, sr)
        wander = 1.0 + WANDER_DEPTH * groups[octave]
        harmonic += amp * wander * np.cos(2.0 * np.pi * k * rev_hz_exact * t + phase)
        harmonic_energy += 0.5 * amp * amp
        noise_spec_mag[max(1, peak_bin - 2) : peak_bin + 3] = floor

    # -- fresh noise, exact residual PSD --------------------------------------
    kernel = 9
    padded = np.pad(noise_spec_mag, kernel // 2, mode="edge")
    env = np.array([np.median(padded[i : i + kernel]) for i in range(len(noise_spec_mag))])
    out_freqs = np.fft.rfftfreq(out_len, 1.0 / sr)
    env_out = np.interp(out_freqs, src_freqs, env)
    phases = rng.uniform(0.0, 2.0 * np.pi, len(env_out))
    nspec = env_out * np.exp(1j * phases)
    nspec[0] = 0.0
    noise = np.fft.irfft(nspec, out_len)
    orig_power = float(np.mean(x**2))
    noise_power_target = max(orig_power - harmonic_energy, 0.02 * orig_power)
    noise *= np.sqrt(noise_power_target / (np.mean(noise**2) + 1e-12))

    # -- firing-modulated mix: fit depth to the cut's roughness ---------------
    target_rough = roughness_index(x, sr, f_fire)
    s = firing_wave(rng, out_len, revs, sr)

    def mix(m: float) -> tuple[np.ndarray, float]:
        gate = np.maximum(0.05, 1.0 + m * s)
        gate /= np.sqrt(np.mean(gate**2))  # keep the noise power (and PSD) put
        y = harmonic + noise * gate
        y = y * np.sqrt(orig_power / (np.mean(y**2) + 1e-12))
        return y, roughness_index(y, sr, f_fire)

    if FORCE_MOD is not None:
        m = FORCE_MOD
        out, rough = mix(m)
    else:
        best = None
        for cand in MOD_DEPTHS:
            y, rough = mix(cand)
            err = abs(rough - target_rough)
            if best is None or err < best[0]:
                best = (err, cand, rough, y)
        _err, m, rough, out = best
    peak = np.max(np.abs(out))
    if peak > 0.97:
        out = out / peak * 0.97

    os.makedirs(STAGE_DIR, exist_ok=True)
    sf.write(os.path.join(STAGE_DIR, f"{band}_pulse.wav"), out.astype(np.float32), sr)
    sf.write(
        os.path.join(LICENSED_ENGINE, f"{band}.wav"), out.astype(np.float32), sr,
        subtype="PCM_16",
    )
    print(
        f"{band:8s} rev {rev_hz:5.2f} Hz  {revs} revs -> {out_len/sr:4.2f}s  "
        f"mod depth {m:.1f}  roughness {target_rough:.2f} -> {rough:.2f}"
    )


def main() -> None:
    for i, (band, native) in enumerate(BANDS):
        synthesize(band, native, i)
    print("\nNOT mirrored anywhere -- owner's ear gates first (see STATUS).")


if __name__ == "__main__":
    main()
