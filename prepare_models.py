"""Download the pinned diarization model and optional Whisper weights."""

import argparse
from config import MODEL_ID, REVISION, WHISPER_CACHE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diarization-only", action="store_true")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download

    snapshot_download(
        MODEL_ID, revision=REVISION, allow_patterns=["*.json", "*.safetensors", "*.txt"]
    )
    if not args.diarization_only:
        import whisper

        whisper.load_model("turbo", device="cpu", download_root=str(WHISPER_CACHE))
    print("Model preparation complete. Run: bash start.sh")


if __name__ == "__main__":
    main()
