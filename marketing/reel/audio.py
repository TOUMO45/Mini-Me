"""Synthesize the reel's sound design, synced to the same timeline as index.html. Output: sfx.wav (48 kHz stereo)."""
import wave
import numpy as np

SR = 48000
DUR = 32.5
N = int(SR * DUR)
rng = np.random.default_rng(7)
L = np.zeros(N)
R = np.zeros(N)

SCENES = [0, 3.3, 5.7, 11.8, 17.3, 25.3, 28.8, 32.5]
FIXES = [0.3, 0.9, 1.35, 1.7, 1.95, 2.15, 2.3, 2.42, 2.52, 2.61, 2.69, 2.76]


def t_arr(n):
    return np.arange(n) / SR


def place(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N:
        return
    sig = sig[: N - i] * gain
    L[i:i + len(sig)] += sig * (1 - max(pan, 0))
    R[i:i + len(sig)] += sig * (1 + min(pan, 0))


def smooth(x, k):
    return np.convolve(x, np.ones(k) / k, mode="same")


def tick(freq=2200, dec=0.012, length=0.08):
    t = t_arr(int(length * SR))
    return (np.sin(2 * np.pi * freq * t) * 0.7 + rng.normal(0, 0.3, len(t))) * np.exp(-t / dec)


def pop(f0=380, f1=900, length=0.16):
    t = t_arr(int(length * SR))
    f = f0 + (f1 - f0) * (t / length) ** 0.5
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.05)


def chime(notes=(659.25, 987.77), gap=0.09, dec=0.55):
    out = np.zeros(int((gap * len(notes) + dec * 3) * SR))
    for k, f in enumerate(notes):
        t = t_arr(int(dec * 3 * SR))
        s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t / dec)
        s[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
        i = int(k * gap * SR)
        out[i:i + len(s)] += s[: len(out) - i]
    return out


def whoosh(length=0.42, bright=True):
    t = t_arr(int(length * SR))
    n = rng.normal(0, 1, len(t))
    n = n - smooth(n, 6 if bright else 30)  # high-pass-ish
    n = smooth(n, 3)
    env = np.sin(np.pi * t / length) ** 2
    return n * env


def thump(f=110, length=0.22):
    t = t_arr(int(length * SR))
    f_t = f * (1 + 1.5 * np.exp(-t / 0.02))
    return np.sin(2 * np.pi * np.cumsum(f_t) / SR) * np.exp(-t / 0.07)


def riser(length, start_f=200, end_f=1800):
    t = t_arr(int(length * SR))
    n = rng.normal(0, 1, len(t))
    out = np.zeros_like(n)
    # crude time-varying band: mix two smoothings whose width shrinks over time
    for a, b in ((0, 0.5), (0.5, 1.0)):
        i0, i1 = int(a * len(t)), int(b * len(t))
        k = int(SR / (start_f + (end_f - start_f) * (a + b) / 2))
        seg = n[i0:i1]
        out[i0:i1] = seg - smooth(seg, max(k, 2))
    env = (t / length) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(start_f / 4 + (end_f / 4 - start_f / 4) * (t / length)) / SR)
    return out * env * 0.6 + tone * env * 0.25


def pad(start, end, freqs, gain=0.12, attack=1.2, release=1.5):
    n = int((end - start) * SR)
    t = t_arr(n)
    s = np.zeros(n)
    for k, f in enumerate(freqs):
        for det in (-0.6, 0.6):
            s += np.sin(2 * np.pi * (f + det) * t + k)
    s /= 2 * len(freqs)
    s *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.25 * t)
    env = np.minimum(1, t / attack) * np.minimum(1, (end - start - t) / release)
    place(s * env, start, gain)


# --- hook: tension riser + accelerating ticks + heartbeat
place(riser(3.2), 0.05, 0.22)
for i, f in enumerate(FIXES):
    place(tick(2000 + 60 * i), f, 0.32, pan=(-0.3 if i % 2 else 0.3))
for b in (0.3, 1.1, 1.8, 2.35):
    place(thump(70, 0.3), b, 0.35)
place(thump(90, 0.4), 2.35, 0.5)  # "Again."

pad(0.0, 3.4, [55.0, 82.41, 110.0], 0.10, attack=0.4, release=0.3)

# --- transitions
for b in SCENES[1:-1]:
    place(whoosh(0.44), b - 0.24, 0.16)

# --- brand drop
place(thump(55, 0.6), 3.3, 0.55)
place(pop(), 3.42, 0.45)
place(pop(500, 1100, 0.12), 4.45, 0.3)

# --- learn
place(tick(1500, 0.02), 6.7, 0.25)
place(whoosh(0.3), 7.3, 0.08)
for k in range(0, 35, 2):
    place(tick(3200, 0.004, 0.02), 8.2 + k / 30, 0.08, pan=0.2)
place(chime(), 9.6, 0.14)

# --- scope stamps
for at in (13.08, 13.88, 14.68):
    place(thump(130, 0.2), at, 0.45)
    place(tick(1800, 0.01), at, 0.18)

# --- recall
for k in range(0, 26, 2):
    place(tick(3200, 0.004, 0.02), 17.95 + k / 26, 0.08, pan=-0.2)
place(riser(0.95, 400, 2400), 19.8, 0.12)
for i in range(7):
    at = 17.3 + 4.15 + i * 0.2
    if i < 5:
        place(tick(1700 + 120 * i, 0.03), at, 0.2)
    else:
        place(thump(160, 0.18), at, 0.35)
place(chime((783.99, 1174.66, 1567.98), 0.07, 0.6), 23.35, 0.13)

# --- trust
for k, at in enumerate((26.25, 26.42, 26.59)):
    place(pop(450 + 80 * k, 1000 + 120 * k, 0.12), at, 0.25)

# --- CTA
place(thump(55, 0.6), 28.8, 0.4)
place(pop(), 28.9, 0.4)
place(chime((523.25, 659.25, 783.99, 1046.5), 0.08, 0.8), 30.15, 0.14)

# --- music bed: warm pad that changes colour per section
pad(3.3, 11.9, [110.0, 164.81, 220.0, 277.18, 329.63])            # A major
pad(11.7, 17.4, [98.0, 146.83, 196.0, 246.94, 293.66])            # G major
pad(17.2, 25.4, [87.31, 130.81, 174.61, 220.0, 261.63], 0.13)     # F major
pad(25.2, 32.5, [110.0, 164.81, 220.0, 277.18, 329.63, 440.0], 0.14, release=2.2)

# master: soft clip, fade out
mix = np.stack([L, R], axis=1)
mix = np.tanh(mix * 1.4) / 1.4
fade = int(0.8 * SR)
mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
mix /= max(1e-9, np.abs(mix).max()) / 0.9
with wave.open("sfx.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((mix * 32767).astype("<i2").tobytes())
print("wrote sfx.wav", DUR, "s")
