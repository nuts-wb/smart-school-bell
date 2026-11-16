"""Membuat nada bel pengganti (WAV) di static/sounds/bel/.
Ganti dengan file bel asli Anda (nama file sama) bila ada."""
import math, os, struct, wave

SR = 22050
OUT = os.path.join(os.path.dirname(__file__), '..', 'static', 'sounds', 'bel')
os.makedirs(OUT, exist_ok=True)

PARTIALS = [(1.0, 1.0, 2.2), (2.0, 0.55, 3.0), (2.76, 0.4, 3.6), (5.4, 0.2, 5.0), (8.93, 0.1, 7.0)]

def strike(freq, dur=1.6):
    n = int(SR * dur)
    buf = [0.0] * n
    for ratio, amp, decay in PARTIALS:
        w = 2 * math.pi * freq * ratio / SR
        for i in range(n):
            t = i / SR
            buf[i] += amp * math.exp(-decay * t) * math.sin(w * i)
    return buf

def mix(notes, total):
    n = int(SR * total)
    out = [0.0] * n
    for start, freq, dur in notes:
        s = strike(freq, dur)
        off = int(start * SR)
        for i, v in enumerate(s):
            if off + i < n:
                out[off + i] += v
    peak = max(abs(v) for v in out) or 1
    return [v / peak * 0.85 for v in out]

def save(name, samples):
    with wave.open(os.path.join(OUT, name), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes(b''.join(struct.pack('<h', int(v * 32767)) for v in samples))

save('bel_masuk.wav', mix([(0, 1046.5, 1.8), (1.0, 1046.5, 1.8), (2.0, 1046.5, 2.0)], 4.0))
save('bel_istirahat.wav', mix([(0, 784, 1.5), (0.8, 659.3, 1.8), (2.0, 784, 1.5), (2.8, 659.3, 1.8)], 4.8))
save('bel_pulang.wav', mix([(0, 1046.5, 1.4), (0.7, 880, 1.4), (1.4, 784, 1.4), (2.1, 523.3, 2.2)], 4.3))
save('notif.wav', mix([(0, 880, 0.7), (0.25, 1318.5, 0.9)], 1.2))
print('selesai')
