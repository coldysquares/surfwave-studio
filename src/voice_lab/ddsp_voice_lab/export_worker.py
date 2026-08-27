from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description="Experimental native TFLite export for the DDSP VST decoder.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    import tensorflow as tf
    from ddsp.training import inference

    model_dir = Path(args.model_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not model_dir.exists():
        raise SystemExit(f"No model directory: {model_dir}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_model_dir = output_dir / "saved_model"

    print("Restoring VST stateless control decoder...")
    model = inference.VSTStatelessPredictControls(str(model_dir))
    print("Writing TensorFlow SavedModel...")
    model.save_model(str(saved_model_dir))

    print("Converting SavedModel to TFLite...")
    converter = tf.lite.TFLiteConverter.from_saved_model(str(saved_model_dir))
    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS,
    ]
    payload = converter.convert()
    tflite_path = output_dir / f"{args.project}.tflite"
    tflite_path.write_bytes(payload)

    manifest = {
        "project": args.project,
        "format": "vst_stateless_predict_controls",
        "tensorflow": tf.__version__,
        "note": (
            "Experimental decoder-only TFLite export generated without tensorflowjs "
            "or tflite-support. Surfwave Studio does not require this file."
        ),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {tflite_path}")


if __name__ == "__main__":
    main()
