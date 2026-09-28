"""Local ASR and explicit timestamp-based speaker assignment; no face recognition."""

import json
from pathlib import Path
from config import WHISPER_CACHE


def align_words(asr_segments, diar_segments):
    rows = []
    for seg in asr_segments:
        words = seg.get("words") or [
            {"start": seg["start"], "end": seg["end"], "word": seg["text"]}
        ]
        for word in words:
            start, end = float(word["start"]), float(word["end"])
            text = word["word"]
            if not text.strip():
                continue
            scores = {}
            for s in diar_segments:
                overlap = max(0, min(end, s["end"]) - max(start, s["start"]))
                if overlap:
                    scores[s["speaker"]] = scores.get(s["speaker"], 0) + overlap
            ranked = sorted(scores, key=scores.get, reverse=True)
            span = max(0.01, end - start)
            speaker = ranked[0] if ranked and scores[ranked[0]] / span >= 0.25 else None
            uncertain = speaker is None or (
                len(ranked) > 1 and scores[ranked[1]] / span >= 0.25
            )
            if (
                rows
                and rows[-1]["speaker"] == speaker
                and rows[-1]["uncertain"] == uncertain
                and start - rows[-1]["end"] < 0.8
                and end - rows[-1]["start"] <= 8
                and len(rows[-1]["text"]) + len(text) <= 65
            ):
                rows[-1]["text"] += text
                rows[-1]["end"] = end
            else:
                rows.append(
                    {
                        "start": start,
                        "end": end,
                        "speaker": speaker,
                        "text": text,
                        "uncertain": uncertain,
                    }
                )
    return rows


def transcribe(p, update):
    import whisper, torch, os

    p = Path(p)
    update(p, status="running", stage="日本語を文字起こししています（Whisper）")
    model = whisper.load_model("turbo", device="cuda", download_root=str(WHISPER_CACHE))
    raw = model.transcribe(
        str(p / "audio.wav"),
        language="ja",
        task="transcribe",
        word_timestamps=True,
        fp16=True,
        verbose=False,
        temperature=0,
        condition_on_previous_text=False,
    )
    (p / "whisper-raw.json").write_text(json.dumps(raw, ensure_ascii=False))
    d = json.loads((p / "result.json").read_text())
    d["transcript"] = align_words(raw["segments"], d["segments"])
    d["asr"] = {
        "model": "openai/whisper-large-v3-turbo",
        "package_version": whisper.__version__,
        "language": "ja",
        "word_timestamps": True,
        "temperature": 0,
        "condition_on_previous_text": False,
        "assignment": "maximum temporal overlap, unidentified below 25%; ambiguous when second speaker overlaps >=25%",
    }
    t = p / "result.json.tmp"
    t.write_text(json.dumps(d, ensure_ascii=False))
    t.replace(p / "result.json")
    del model
    torch.cuda.empty_cache()
    return len(d["transcript"])
