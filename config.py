"""Shared model and local storage settings."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DIARIZATION_DATA", ROOT / "data")).resolve()
WHISPER_CACHE = Path(os.environ.get("WHISPER_CACHE", ROOT / ".cache" / "whisper"))
MODEL_ID = "nvidia/Nemotron-3-Diarization"
REVISION = "f667ed73aee57d40cc39428eb768b4fd87a0a29e"
