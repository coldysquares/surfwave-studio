from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np

SAMPLE_RATE = 16000
MODEL_SECONDS = 4.0
CHUNK_SAMPLES = int(SAMPLE_RATE * MODEL_SECONDS)
OVERLAP_SAMPLES = int(SAMPLE_RATE * 0.10)  # 100 ms
HOP_SAMPLES = CHUNK_SAMPLES - OVERLAP_SAMPLES

def parse_bool(v: str) -> bool:
    return str(v).lower() in {"1", "true", "yes", "on"}

def overlap_add(chunks: list[np.ndarray], total_len: int) -> np.ndarray:
    if not chunks:
        return np.zeros(total_len, np.float32)

    out_len = HOP_SAMPLES * max(0, len(chunks) - 1) + CHUNK_SAMPLES
    out = np.zeros(out_len, np.float32)
    weight = np.zeros(out_len, np.float32)

    fade = np.ones(CHUNK_SAMPLES, np.float32)
    if OVERLAP_SAMPLES:
        ramp = np.linspace(0.0, 1.0, OVERLAP_SAMPLES, dtype=np.float32)
        fade[:OVERLAP_SAMPLES] = ramp
        fade[-OVERLAP_SAMPLES:] = ramp[::-1]

    for i, chunk in enumerate(chunks):
        start = i * HOP_SAMPLES
        end = start + CHUNK_SAMPLES
        out[start:end] += chunk[:CHUNK_SAMPLES] * fade
        weight[start:end] += fade

    weight = np.maximum(weight, 1e-6)
    out /= weight
    return out[:total_len]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--pitch_semitones", type=float, default=0.0)
    p.add_argument("--harmonic_gain", type=float, default=1.0)
    p.add_argument("--noise_gain", type=float, default=1.0)
    p.add_argument("--reverb", default="false")
    args = p.parse_args()

    import librosa
    import soundfile as sf
    import tensorflow as tf
    import gin
    import ddsp
    import ddsp.training
    from ddsp.training import inference

    from .projects import project_dir

    model_dir = project_dir(args.project) / "model"
    if not model_dir.exists():
        raise FileNotFoundError(f"No model directory: {model_dir}")

    print("Loading audio...")
    audio, _ = librosa.load(args.input, sr=SAMPLE_RATE, mono=True)
    audio = audio.astype(np.float32)
    original_len = len(audio)
    if original_len < 1:
        raise ValueError("Input audio is empty.")

    print("Loading DDSP checkpoint...")
    with gin.unlock_config():
        inference.parse_operative_config(str(model_dir))
        # This improves phase accumulation accuracy for offline rendering.
        gin.parse_config("oscillator_bank.use_angular_cumsum = True")

    model = ddsp.training.models.Autoencoder()
    model.restore(str(model_dir))

    pitch_ratio = 2.0 ** (args.pitch_semitones / 12.0)
    use_reverb = parse_bool(args.reverb)

    rendered = []
    starts = list(range(0, max(1, original_len), HOP_SAMPLES))
    for index, start in enumerate(starts, 1):
        chunk = audio[start:start + CHUNK_SAMPLES]
        if len(chunk) < CHUNK_SAMPLES:
            chunk = np.pad(chunk, (0, CHUNK_SAMPLES - len(chunk)))

        # CREPE/f0 extraction at the same 50 Hz frame rate used by the VST-style DDSP model.
        # Local-average decoding avoids the obsolete hmmlearn 0.2.x Viterbi dependency on Apple Silicon.
        f0_hz, f0_conf = ddsp.spectral_ops.compute_f0(
            chunk,
            frame_rate=50,
            viterbi=False,
            padding="center",
        )
        f0_hz = np.asarray(f0_hz, dtype=np.float32) * pitch_ratio
        f0_conf = np.asarray(f0_conf, dtype=np.float32)

        features = {
            "audio": chunk[np.newaxis, :],
            "audio_16k": chunk[np.newaxis, :],
            "f0_hz": f0_hz[np.newaxis, :],
            "f0_confidence": f0_conf[np.newaxis, :],
        }

        # Decode controls, then synthesize the harmonic/noise paths separately
        # so the user can actually manipulate the physical channels.
        feats = model.encode(dict(features), training=False)
        feats.update(model.decoder(feats, training=False))
        pg = model.processor_group

        harmonic = pg.harmonic(
            feats["amps"],
            feats["harmonic_distribution"],
            feats["f0_hz"],
        )
        noise = pg.filtered_noise(feats["noise_magnitudes"])

        mixed = harmonic * float(args.harmonic_gain) + noise * float(args.noise_gain)
        if use_reverb:
            mixed = pg.reverb(mixed)
        out = pg.crop(mixed)
        out = np.asarray(out.numpy()[0], dtype=np.float32)

        if len(out) < CHUNK_SAMPLES:
            out = np.pad(out, (0, CHUNK_SAMPLES - len(out)))
        rendered.append(out[:CHUNK_SAMPLES])
        print(f"Rendered chunk {index}/{len(starts)}")

        if start + CHUNK_SAMPLES >= original_len:
            break

    final = overlap_add(rendered, original_len)
    peak = float(np.max(np.abs(final))) if len(final) else 0.0
    if peak > 0.999:
        final = final / peak * 0.98

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), final, SAMPLE_RATE, subtype="PCM_24")
    print(f"Saved {output}")

if __name__ == "__main__":
    main()
