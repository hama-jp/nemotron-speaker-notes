#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
for executable in ffmpeg ffprobe; do
  command -v "$executable" >/dev/null || { echo "Missing executable: $executable" >&2; exit 1; }
done
exec python -m uvicorn server:app --host 127.0.0.1 --port "${PORT:-18763}"
