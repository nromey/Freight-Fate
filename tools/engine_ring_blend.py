"""Ring rebuild final recipe (owner's pick): shallow synth + PV-stretched real.

The owner's ear converged here across the rounds: the firing-modulated
synth bed at a SHALLOW depth (m=0.15 -- deeper reads as a raspberry, none
reads as a jet), blended with a PHASE-VOCODER time-stretch of the approved
real cut. The stretch is what makes the real layer legal again: 2 s of
recording spread over ~5 s repeats nothing inside the loop, so it donates
genuine diesel texture without donating a fingerprint. Each layer masks
the other's flaw -- the synth hides PV smearing, the real hides synthetic
regularity.

Output per band: blend of
  - engine_ring_pulse synthesis at FORCE_MOD = BLEND_SYNTH_MOD
  - a phase-vocoder stretch of sound-source/ring-round0/<band>_original.wav
    to the same length, wrap-spliced circular
mixed at BLEND_REAL_GAIN (equal-power), RMS-matched to the original.

STAGE_ONLY=True writes mid-band candidates to the staging dir for the
owner's ear; flip to False to render and install all four bands. Nothing
is mirrored anywhere by this tool.

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
STAGE_DIR = r"C:\temp\ffsound\round2\brackets"

STAGE_ONLY = True
BLEND_SYNTH_MOD = 0.15  # owner bracket pick
BLEND_REAL_GAIN = 0.6  # real layer share (equal-power: synth gets sqrt(1-g^2))
PV_FFT = 2048
PV_HOP_S = 512
SPLICE_S = 0.03

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


def pv_stretch(x: np.ndarray, out_len: int, sr: int) -> np.ndarray:
    """Classic phase-vocoder time stretch to ``out_len`` samples."""
    ratio = out_len / len(x)
    hop_a = PV_HOP_S / ratio
    window = np.hanning(PV_FFT)
    omega = 2.0 * np.pi * np.arange(PV_FFT // 2 + 1) * 1.0 / PV_FFT
    n_frames = int((out_len - PV_FFT) / PV_HOP_S)
    out = np.zeros(out_len + PV_FFT)
    norm = np.zeros(out_len + PV_FFT)
    phase_acc = None
    prev_phase = None
    for i in range(n_frames):
        a = int(round(i * hop_a))
        if a + PV_FFT > len(x):
            a = len(x) - PV_FFT
        frame = np.fft.rfft(x[a : a + PV_FFT] * window)
        mag, phase = np.abs(frame), np.angle(frame)
        if phase_acc is None:
            phase_acc = phase.copy()
        else:
            delta = phase - prev_phase - omega * hop_a
            delta = np.mod(delta + np.pi, 2.0 * np.pi) - np.pi
            true_freq = omega + delta / hop_a
            phase_acc = phase_acc + true_freq * PV_HOP_S
        prev_phase = phase
        s = i * PV_HOP_S
        out[s : s + PV_FFT] += np.fft.irfft(mag * np.exp(1j * phase_acc), PV_FFT) * window
        norm[s : s + PV_FFT] += window**2
    out = out[:out_len] / np.maximum(norm[:out_len], 1e-6)
    # Wrap splice: crossfade the tail into the head's material (linear --
    # correlated near-periodic ends), same recipe as fix_loop_seams.
    w = int(SPLICE_S * sr)
    head = out[:w].copy()
    y = out[w:].copy()
    ramp = np.linspace(0.0, 1.0, w)
    y[-w:] = y[-w:] * (1.0 - ramp) + head * ramp
    return y


def render_band(mod, band: str, native: float, index: int) -> tuple[np.ndarray, int]:
    """The blend: shallow-mod synthesis + PV-stretched real, equal-power."""
    mod.FORCE_MOD = BLEND_SYNTH_MOD
    mod.synthesize(band, native, index)  # writes overlay + stage; reread it
    synth, sr = sf.read(os.path.join(mod.LICENSED_ENGINE, f"{band}.wav"), dtype="float64")
    real, sr2 = sf.read(os.path.join(ROUND0, f"{band}_original.wav"), dtype="float64")
    assert sr == sr2
    stretched = pv_stretch(real, len(synth) + int(SPLICE_S * sr), sr)[: len(synth)]
    if len(stretched) < len(synth):
        stretched = np.pad(stretched, (0, len(synth) - len(stretched)), mode="wrap")
    stretched *= np.sqrt(np.mean(real**2) / (np.mean(stretched**2) + 1e-12))
    g_real = BLEND_REAL_GAIN
    g_synth = float(np.sqrt(1.0 - g_real**2))
    out = stretched * g_real + synth * g_synth
    out *= np.sqrt(np.mean(real**2) / (np.mean(out**2) + 1e-12))
    peak = np.max(np.abs(out))
    if peak > 0.97:
        out = out / peak * 0.97
    return out, sr


def main() -> None:
    mod = _pulse_module()
    os.makedirs(STAGE_DIR, exist_ok=True)
    bands = BANDS if not STAGE_ONLY else (BANDS[1],)  # mid first for the ear
    for band, native in bands:
        index = BANDS.index((band, native))
        out, sr = render_band(mod, band, native, index)
        stage_path = os.path.join(STAGE_DIR, f"{band}_m015_pv_blend.wav")
        sf.write(stage_path, out.astype(np.float32), sr)
        if not STAGE_ONLY:
            sf.write(
                os.path.join(LICENSED_ENGINE, f"{band}.wav"),
                out.astype(np.float32),
                sr,
                subtype="PCM_16",
            )
        # Also stage the pure PV stretch for reference listening.
        real, sr2 = sf.read(os.path.join(ROUND0, f"{band}_original.wav"), dtype="float64")
        pv_only = pv_stretch(real, len(out) + int(SPLICE_S * sr2), sr2)[: len(out)]
        pv_only *= np.sqrt(np.mean(real**2) / (np.mean(pv_only**2) + 1e-12))
        sf.write(
            os.path.join(STAGE_DIR, f"{band}_pv_only.wav"), pv_only.astype(np.float32), sr2
        )
        print(f"{band}: staged m015+pv blend (real {BLEND_REAL_GAIN:.0%}) and pv-only")
    if STAGE_ONLY:
        print("\nSTAGE_ONLY: overlay holds the plain synth; blend is staged for the ear.")


if __name__ == "__main__":
    main()
