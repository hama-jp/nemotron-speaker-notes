from __future__ import annotations
import json, os, re, shutil, subprocess, threading, uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import ROOT, DATA, MODEL_ID, REVISION

DATA.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 2 * 1024**3
MAX_SECONDS = 3600
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()
MODEL = None
PROCESSOR = None
app = FastAPI(
    title="Nemotron Japanese Meeting Diarization", docs_url=None, redoc_url=None
)
ALLOWED = {
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".opus",
}


def jobdir(job_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", job_id):
        raise HTTPException(404)
    p = DATA / job_id
    if not (p / "job.json").exists():
        raise HTTPException(404)
    return p


def read_job(p):
    return json.loads((p / "job.json").read_text())


def update(p, **kwargs):
    with LOCK:
        f = p / "job.json"
        d = json.loads(f.read_text()) if f.exists() else {}
        d.update(kwargs)
        t = p / "job.json.tmp"
        t.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        t.replace(f)
    return d


def probe(path):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    x = json.loads(r.stdout)
    duration = float(x["format"]["duration"])
    if not 0 < duration <= MAX_SECONDS:
        raise ValueError("音声の長さは1時間以内にしてください。")
    if not any(s["codec_type"] == "audio" for s in x["streams"]):
        raise ValueError("音声トラックが見つかりません。")
    return duration, any(s["codec_type"] == "video" for s in x["streams"])


def write_result(p, audio, sr, logits, segments, environment):
    import numpy as np

    # Frames are exactly 10 ms. Plotting takes mean probability in each 100 ms bin.
    raw = logits.detach().float().cpu().numpy() if hasattr(logits, "detach") else logits
    if raw.ndim == 3:
        raw = raw[0]
    probs = 1 / (1 + np.exp(-np.clip(raw, -60, 60)))
    bins = [
        np.round(probs[i : i + 10].mean(0), 4).tolist()
        for i in range(0, len(probs), 10)
    ]
    step = max(1, int(len(audio) / 2000))
    wave = [
        round(float(np.max(np.abs(audio[i : i + step]))), 4)
        for i in range(0, len(audio), step)
    ]
    result = {
        "duration": len(audio) / sr,
        "segments": segments,
        "speakers": sorted({s["speaker"] for s in segments}),
        "probabilities": bins,
        "probability_step": 0.1,
        "waveform": wave,
        "model": MODEL_ID,
        "revision": REVISION,
        "environment": environment,
        "threshold": 0.5,
    }
    (p / "result.json").write_text(json.dumps(result, ensure_ascii=False))
    with (p / "speakers.rttm").open("w") as f:
        for s in segments:
            f.write(
                f"SPEAKER {p.name} 1 {s['start']:.2f} {s['end'] - s['start']:.2f} <NA> <NA> speaker_{s['speaker'] + 1} <NA> <NA>\n"
            )
    update(p, duration=result["duration"], speakers=len(result["speakers"]))


def process(p):
    global MODEL, PROCESSOR
    try:
        import numpy as np, soundfile as sf, torch, transformers
        from transformers import AutoProcessor, AutoModelForAudioFrameClassification

        update(p, status="running", stage="音声を準備しています")
        meta = read_job(p)
        source = p / meta["source_file"]
        duration, has_video = probe(source)
        wav = p / "audio.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(wav),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        if has_video:
            update(p, stage="ブラウザ用の動画を準備しています")
            media = p / "preview.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-vf",
                    "scale='min(1280,iw)':-2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "24",
                    "-threads",
                    "4",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(media),
                ],
                check=True,
                capture_output=True,
                timeout=1800,
            )
            media_name = "preview.mp4"
        else:
            media_name = "audio.wav"
        update(
            p,
            has_video=has_video,
            media_file=media_name,
            duration=duration,
            stage="モデルを読み込んでいます",
        )
        audio, sr = sf.read(wav, dtype="float32")
        assert sr == 16000 and audio.ndim == 1 and np.isfinite(audio).all()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPUを利用できません。")
        torch.set_num_threads(4)
        with MODEL_LOCK:
            if MODEL is None:
                PROCESSOR = AutoProcessor.from_pretrained(
                    MODEL_ID, revision=REVISION, local_files_only=True
                )
                MODEL = (
                    AutoModelForAudioFrameClassification.from_pretrained(
                        MODEL_ID,
                        revision=REVISION,
                        dtype=torch.float32,
                        local_files_only=True,
                    )
                    .to("cuda")
                    .eval()
                )
            update(p, stage="音声から話者区間を推定しています")
            inputs = PROCESSOR(audio, sampling_rate=sr, return_tensors="pt").to(
                MODEL.device, dtype=MODEL.dtype
            )
            with torch.inference_mode():
                logits = MODEL(**inputs).logits
            assert torch.isfinite(logits).all()
            segments = [
                {
                    "start": float(s["Start"]),
                    "end": float(s["End"]),
                    "speaker": int(s["Speaker"]),
                }
                for s in PROCESSOR.extract_speaker_dict(logits, inputs.attention_mask)[
                    0
                ]
            ]
            assert all(
                0 <= s["start"] < s["end"] <= len(audio) / sr + 0.1
                and 0 <= s["speaker"] < 8
                for s in segments
            )
            env = {
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "gpu": torch.cuda.get_device_name(),
                "dtype": str(MODEL.dtype),
                "mode": "offline, default internal chunks",
            }
            write_result(p, audio, sr, logits, segments, env)
        if meta.get("transcribe", True):
            from transcription import transcribe

            try:
                transcribe(p, update)
            except Exception as exc:
                import traceback

                (p / "asr-error.log").write_text(traceback.format_exc())
                update(
                    p,
                    asr_error="文字起こしに失敗しました。話者推定は利用できます。 "
                    + str(exc)[:160],
                )
        update(p, status="done", stage="解析完了")
    except Exception as exc:
        import traceback

        (p / "error.log").write_text(traceback.format_exc())
        update(p, status="error", stage="解析できませんでした", error=str(exc)[:500])


@app.middleware("http")
async def origin_check(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method in {"POST", "PUT", "DELETE"}
        and origin
        and origin.rstrip("/") != str(request.base_url).rstrip("/")
    ):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"detail": "別サイトからの操作は受け付けません。"}, status_code=403
        )
    return await call_next(request)


@app.get("/api/jobs")
def jobs():
    return [
        read_job(p)
        for p in sorted(DATA.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if p.is_dir() and (p / "job.json").exists()
    ]


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), transcribe: bool = Form(True)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "動画または音声ファイルを選んでください。")
    active = [
        p
        for p in DATA.iterdir()
        if (p / "job.json").exists()
        and read_job(p).get("status") in {"queued", "running", "uploading"}
    ]
    if len(active) >= 3:
        raise HTTPException(
            429, "処理待ちが3件あります。完了してから追加してください。"
        )
    if shutil.disk_usage(DATA).free < 8 * 1024**3:
        raise HTTPException(507, "保存先の空き容量が不足しています。")
    jid = uuid.uuid4().hex
    p = DATA / jid
    p.mkdir()
    source = "original" + suffix
    update(
        p,
        id=jid,
        name=Path(file.filename or "audio").name,
        source_file=source,
        status="uploading",
        stage="アップロード中",
        transcribe=transcribe,
    )
    try:
        size = 0
        with (p / source).open("wb") as out:
            while chunk := await file.read(1024**2):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "ファイルは2GB以内にしてください。")
                out.write(chunk)
        if not size:
            raise HTTPException(400, "空のファイルです。")
    except BaseException:
        shutil.rmtree(p)
        raise
    finally:
        await file.close()
    update(p, status="queued", stage="解析待ち")
    POOL.submit(process, p)
    return read_job(p)


@app.get("/api/jobs/{jid}")
def job(jid: str):
    return read_job(jobdir(jid))


@app.get("/api/jobs/{jid}/result")
def result(jid: str):
    p = jobdir(jid)
    if read_job(p)["status"] != "done":
        raise HTTPException(409, "解析はまだ完了していません。")
    return FileResponse(p / "result.json", media_type="application/json")


@app.get("/api/jobs/{jid}/media")
def media(jid: str):
    p = jobdir(jid)
    name = read_job(p).get("media_file")
    if not name:
        raise HTTPException(409, "メディアを準備しています。")
    return FileResponse(
        p / name, media_type="video/mp4" if name.endswith(".mp4") else "audio/wav"
    )


@app.get("/api/jobs/{jid}/rttm")
def rttm(jid: str):
    p = jobdir(jid)
    if not (p / "speakers.rttm").exists():
        raise HTTPException(409)
    return FileResponse(
        p / "speakers.rttm", filename="speakers.rttm", media_type="text/plain"
    )


@app.on_event("startup")
def recover():
    for p in DATA.iterdir():
        if (p / "job.json").exists() and read_job(p).get("status") in {
            "queued",
            "running",
            "uploading",
        }:
            update(
                p,
                status="error",
                stage="前回の処理が中断されました",
                error="ファイルをもう一度開いて解析してください。",
            )


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
