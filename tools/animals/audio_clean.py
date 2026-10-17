"""
Shared DSP for turning raw animal recordings into toy-ready clips.
  clean_clip(x)      -> high-pass + spectral-gate denoise of a whole clip
  cut_and_level(...) -> trim [start,end], fade in/out, match loudness, soft-limit
The same loudness rule is implemented in the review page (JavaScript) so what you hear
there is what the render script produces.
Requires: numpy, scipy
"""
import numpy as np
from scipy import signal, ndimage
from scipy.io import wavfile

SR = 44100
TARGET_DB = -23.0          # target "active RMS" level of every final clip (dBFS)
FADE_IN, FADE_OUT = 0.015, 0.12
SOFT_KNEE = 0.6


def load_wav(path):
    sr, x = wavfile.read(path)
    assert sr == SR, f"{path}: expected {SR} Hz, got {sr}"
    x = x.astype(np.float64) / 32768.0 if x.dtype == np.int16 else x.astype(np.float64)
    return x.mean(axis=1) if x.ndim > 1 else x


def save_wav(path, x):
    wavfile.write(path, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def env_db(x, win=0.025, hop=0.010):
    """Short-time RMS in dB, one value per 10 ms."""
    n, h = int(win * SR), int(hop * SR)
    xp = np.pad(x, (n // 2, n // 2))
    w = np.lib.stride_tricks.sliding_window_view(xp, n)[::h]
    return 20 * np.log10(np.sqrt((w ** 2).mean(axis=1)) + 1e-9)


def hpf(x, fc=60):
    sos = signal.butter(4, fc, btype="high", fs=SR, output="sos")
    return signal.sosfiltfilt(sos, x)


def denoise(x, alpha=1.8, floor=0.15, quiet_pct=20):
    """Spectral gating. Noise profile = average spectrum of the quietest 20% of frames.
    Skipped when the clip never goes quiet (continuous sounds like a buzz) because the
    'noise' would then be the animal itself."""
    f, t, S = signal.stft(x, SR, nperseg=2048, noverlap=1536)
    mag = np.abs(S)
    fe = mag.mean(axis=0)
    e_db = 20 * np.log10(fe + 1e-9)
    spread = np.percentile(e_db, 90) - np.percentile(e_db, 10)
    if spread < 10:
        return x, {"denoised": False, "reason": "continuous sound, no quiet gaps to learn the noise from"}
    q = fe <= np.percentile(fe, quiet_pct)
    if q.sum() < 4:
        q = fe <= np.sort(fe)[3]
    nm = mag[:, q].mean(axis=1, keepdims=True)
    G = np.clip(1 - alpha * nm / (mag + 1e-9), floor, 1.0)
    G = ndimage.uniform_filter(G, size=(5, 3))
    _, y = signal.istft(S * G, SR, nperseg=2048, noverlap=1536)
    y = np.pad(y, (0, max(0, len(x) - len(y))))[: len(x)]
    return y, {"denoised": True}


def clean_clip(x):
    x = hpf(x)
    before = np.percentile(env_db(x), 10)
    y, info = denoise(x)
    after = np.percentile(env_db(y), 10)
    info["floor_before_db"] = float(before)
    info["floor_after_db"] = float(after)
    return y, info


def active_rms(x):
    """RMS over the 'active' 20 ms frames (those within 20 dB of the loudest frame)."""
    fr = int(0.02 * SR)
    nf = len(x) // fr
    if nf == 0:
        return float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    r = np.sqrt((x[: nf * fr].reshape(nf, fr) ** 2).mean(axis=1))
    sel = r[r >= r.max() * 0.1]
    return float(np.sqrt(np.mean(sel ** 2)) + 1e-9)


def soft_clip(y, knee=SOFT_KNEE):
    a = np.abs(y)
    out = np.where(a < knee, a, knee + (1 - knee) * np.tanh((a - knee) / (1 - knee)))
    return np.sign(y) * out


def cut_and_level(x, start, end):
    seg = x[int(start * SR): int(end * SR)].copy()
    g = 10 ** (TARGET_DB / 20) / active_rms(seg)
    n = len(seg)
    fi, fo = min(int(FADE_IN * SR), n // 4), min(int(FADE_OUT * SR), n // 4)
    if fi:
        seg[:fi] *= np.linspace(0, 1, fi)
    if fo:
        seg[-fo:] *= np.linspace(1, 0, fo)
    return soft_clip(seg * g)
