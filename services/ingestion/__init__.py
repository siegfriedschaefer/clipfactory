import json
import subprocess
import uuid
from pathlib import Path

from services.storage import video_dir


def probe_video(path: Path) -> dict:
    """Read duration, resolution and fps from a video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr}")

    data = json.loads(result.stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    duration = float(data.get("format", {}).get("duration", 0) or 0)

    if video_stream:
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        resolution = f"{width}x{height}"
        fps_str = video_stream.get("r_frame_rate", "0/1")
        num, den = fps_str.split("/")
        fps = round(float(num) / float(den), 3) if float(den) != 0 else None
    else:
        resolution = None
        fps = None

    return {"duration": duration, "resolution": resolution, "fps": fps}


def normalize_video(video_id: uuid.UUID, raw_path: Path) -> Path:
    """Re-encode video to h264/aac mp4. Returns path to normalized file."""
    out_path = video_dir(video_id) / "normalized.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_path),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # ensure even dimensions
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg normalization failed:\n{result.stderr}")
    return out_path


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
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{result.stderr}")
    return out_path


def run_ingestion(video_id: uuid.UUID, raw_path: Path) -> dict:
    """Full ingestion pipeline: probe → normalize → extract audio.

    Returns a dict with duration, resolution, fps, normalized_path, audio_path.
    """
    metadata = probe_video(raw_path)
    normalized_path = normalize_video(video_id, raw_path)
    audio_path = extract_audio(video_id, normalized_path)
    return {
        "duration": metadata["duration"],
        "resolution": metadata["resolution"],
        "fps": metadata["fps"],
        "normalized_path": normalized_path,
        "audio_path": audio_path,
    }
