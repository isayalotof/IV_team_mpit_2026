"""Voice-to-SQL: transcribe audio to text via Vosk."""
import asyncio
import json
import os
import subprocess
import tempfile
import wave
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from askdata.auth.deps import require_role
from askdata.auth.models import User

router = APIRouter(prefix="/voice", tags=["voice"])

_MODEL_DIR = Path("/app/meta_data/vosk_model")
_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
_vosk_model = None


def _ensure_model() -> Path:
    if _MODEL_DIR.exists():
        return _MODEL_DIR
    import urllib.request
    print("Downloading Vosk model (~45MB)...")
    zip_path = Path("/tmp/vosk_model.zip")
    urllib.request.urlretrieve(_MODEL_URL, zip_path)
    _MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(_MODEL_DIR.parent)
    # rename extracted dir
    extracted = _MODEL_DIR.parent / "vosk-model-small-ru-0.22"
    if extracted.exists():
        extracted.rename(_MODEL_DIR)
    zip_path.unlink(missing_ok=True)
    print(f"Vosk model saved to {_MODEL_DIR}")
    return _MODEL_DIR


def _get_vosk_model():
    global _vosk_model
    if _vosk_model is None:
        from vosk import Model
        model_path = _ensure_model()
        _vosk_model = Model(str(model_path))
    return _vosk_model


def _convert_to_wav_sync(audio_bytes: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(audio_bytes)
        src = f.name
    dst = src + ".wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", dst],
            capture_output=True, check=True, timeout=30,
        )
        with open(dst, "rb") as f:
            return f.read()
    finally:
        os.unlink(src)
        if os.path.exists(dst):
            os.unlink(dst)


def _transcribe_sync(wav_bytes: bytes) -> str:
    from vosk import KaldiRecognizer
    model = _get_vosk_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        wav_path = f.name
    try:
        wf = wave.open(wav_path)
        rec = KaldiRecognizer(model, wf.getframerate())
        parts = []
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                parts.append(json.loads(rec.Result()).get("text", ""))
        parts.append(json.loads(rec.FinalResult()).get("text", ""))
        wf.close()
        return " ".join(p for p in parts if p).strip()
    finally:
        os.unlink(wav_path)


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    current_user: User = Depends(require_role("analyst")),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    loop = asyncio.get_event_loop()
    try:
        wav_bytes = await loop.run_in_executor(None, _convert_to_wav_sync, audio_bytes)
        text = await loop.run_in_executor(None, _transcribe_sync, wav_bytes)
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="Audio conversion failed (ffmpeg error)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")

    return {"text": text}
