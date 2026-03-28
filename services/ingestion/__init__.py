import subprocess
import uuid
from pathlib import Path

from services.storage import video_dir


def extract_audio(video_id: uuid.UUID, video_path: Path) -> Path:
    """Extract audio from a video file to a 16kHz mono WAV.

    Uses ffmpeg. The output is saved alongside the source video as audio.wav.
    Returns the path to the extracted WAV file.
    """
    out_path = video_dir(video_id) / "audio.wav"
    cmd = [
        "ffmpeg",
        "-y",           # overwrite if exists
        "-i", str(video_path),
        "-vn",          # drop video stream
        "-ar", "16000", # 16kHz sample rate (required by moonshine_voice)
        "-ac", "1",     # mono
        "-sample_fmt", "s16",  # 16-bit PCM
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")
    return out_path
