from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_RATE = 50
EXAMPLE_SECONDS = 4.0
HOP_SECONDS = 1.0
ANALYSIS_CHUNK_SECONDS = 20.0
AUDIO_SAMPLES = int(SAMPLE_RATE * EXAMPLE_SECONDS)
HOP_SAMPLES = int(SAMPLE_RATE * HOP_SECONDS)
CHUNK_SAMPLES = int(SAMPLE_RATE * ANALYSIS_CHUNK_SECONDS)
FEATURE_FRAMES = int(EXAMPLE_SECONDS * FRAME_RATE) + 1  # centered framing
FEATURE_HOP = int(HOP_SECONDS * FRAME_RATE)


def float_feature(values, tf):
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    return tf.train.Feature(float_list=tf.train.FloatList(value=arr))


def make_example(audio, f0_hz, f0_confidence, loudness_db, tf):
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    f0_hz = np.asarray(f0_hz, dtype=np.float32).reshape(-1)
    f0_confidence = np.asarray(f0_confidence, dtype=np.float32).reshape(-1)
    loudness_db = np.asarray(loudness_db, dtype=np.float32).reshape(-1)

    if audio.size != AUDIO_SAMPLES:
        raise ValueError(f"Expected {AUDIO_SAMPLES} audio samples, got {audio.size}")
    for name, arr in (
        ("f0_hz", f0_hz),
        ("f0_confidence", f0_confidence),
        ("loudness_db", loudness_db),
    ):
        if arr.size != FEATURE_FRAMES:
            raise ValueError(f"Expected {FEATURE_FRAMES} {name} frames, got {arr.size}")

    features = {
        "audio": float_feature(audio, tf),
        "audio_16k": float_feature(audio, tf),
        "f0_hz": float_feature(f0_hz, tf),
        "f0_confidence": float_feature(f0_confidence, tf),
        "loudness_db": float_feature(loudness_db, tf),
    }
    return tf.train.Example(features=tf.train.Features(feature=features))


def iter_analysis_chunks(audio: np.ndarray):
    """Yield manageable chunks; pad only a final chunk shorter than 4 seconds."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return
    for start in range(0, audio.size, CHUNK_SAMPLES):
        chunk = audio[start:start + CHUNK_SAMPLES]
        if chunk.size < AUDIO_SAMPLES:
            chunk = np.pad(chunk, (0, AUDIO_SAMPLES - chunk.size))
        yield chunk


def window_starts(n_samples: int):
    """Return 1-second-hop starts for complete 4-second examples."""
    if n_samples < AUDIO_SAMPLES:
        return []
    return list(range(0, n_samples - AUDIO_SAMPLES + 1, HOP_SAMPLES))


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a local DDSP TFRecord without Apache Beam."
    )
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    import librosa
    import tensorflow as tf
    import ddsp

    source_dir = Path(args.sources).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    files = sorted(source_dir.glob("*.wav"))
    if not files:
        raise SystemExit(f"No WAV files found in {source_dir}")

    output.parent.mkdir(parents=True, exist_ok=True)
    for stale in output.parent.glob(output.name + "*"):
        if stale.is_file():
            stale.unlink()

    count = 0
    print(f"Preparing {len(files)} WAV file(s) at {SAMPLE_RATE} Hz / {FRAME_RATE} fps")
    print(f"Examples: {EXAMPLE_SECONDS:g}s with {HOP_SECONDS:g}s hops; analysis chunks: {ANALYSIS_CHUNK_SECONDS:g}s")
    print("Pitch tracking: CREPE, local-average decoding (no hmmlearn/Viterbi dependency)")

    with tf.io.TFRecordWriter(str(output)) as writer:
        for file_index, wav in enumerate(files, 1):
            audio, _ = librosa.load(str(wav), sr=SAMPLE_RATE, mono=True)
            audio = np.asarray(audio, dtype=np.float32)
            duration = audio.size / SAMPLE_RATE
            chunks = list(iter_analysis_chunks(audio))
            print(f"[{file_index}/{len(files)}] {wav.name}: {duration:.1f}s -> {len(chunks)} analysis chunk(s)")

            file_examples = 0
            for chunk_index, chunk in enumerate(chunks, 1):
                # Extract features once per analysis chunk rather than re-running
                # CREPE for every overlapping 4-second training example.
                f0_hz, f0_confidence = ddsp.spectral_ops.compute_f0(
                    chunk,
                    frame_rate=FRAME_RATE,
                    viterbi=False,
                    padding="center",
                )
                loudness_db = ddsp.spectral_ops.compute_loudness(
                    chunk,
                    sample_rate=SAMPLE_RATE,
                    frame_rate=FRAME_RATE,
                    n_fft=512,
                    padding="center",
                )

                f0_hz = np.asarray(f0_hz, dtype=np.float32).reshape(-1)
                f0_confidence = np.asarray(f0_confidence, dtype=np.float32).reshape(-1)
                loudness_db = np.asarray(loudness_db, dtype=np.float32).reshape(-1)

                starts = window_starts(chunk.size)
                for start in starts:
                    feature_start = (start // HOP_SAMPLES) * FEATURE_HOP
                    feature_end = feature_start + FEATURE_FRAMES
                    audio_window = chunk[start:start + AUDIO_SAMPLES]
                    if feature_end > min(len(f0_hz), len(f0_confidence), len(loudness_db)):
                        raise RuntimeError(
                            "Feature framing mismatch while preparing DDSP data: "
                            f"need frames {feature_start}:{feature_end}, got "
                            f"f0={len(f0_hz)}, confidence={len(f0_confidence)}, loudness={len(loudness_db)}"
                        )
                    ex = make_example(
                        audio_window,
                        f0_hz[feature_start:feature_end],
                        f0_confidence[feature_start:feature_end],
                        loudness_db[feature_start:feature_end],
                        tf,
                    )
                    writer.write(ex.SerializeToString())
                    count += 1
                    file_examples += 1

                print(f"  chunk {chunk_index}/{len(chunks)} -> {len(starts)} example(s)")

            print(f"  total for {wav.name}: {file_examples} example(s)")

    if count == 0:
        raise SystemExit("No training examples were generated.")
    print(f"Wrote {count} training example(s) -> {output}")


if __name__ == "__main__":
    main()
