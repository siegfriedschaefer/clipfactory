"""Packaging Engine — turns a clip candidate into an exportable 9:16 MP4.

All rendering is done with ffmpeg. No external rendering framework needed.
Steps:
  1. Detect face center from keyframes → compute 9:16 crop x-offset
  2. Generate SRT subtitle file from transcript segments
  3. Run ffmpeg: trim → crop → scale → burn subtitles → (optional) hook overlay
"""
import subprocess
import uuid
from pathlib import Path

import cv2
import numpy as np

_CASCADE_FRONTAL = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_CASCADE_PROFILE = cv2.data.haarcascades + "haarcascade_profileface.xml"
_TARGET_W = 1080
_TARGET_H = 1920
_SAMPLE_FRAMES = 8  # frames to sample per clip for face detection


def _has_libass() -> bool:
    """Return True if this ffmpeg build supports the subtitles (libass) filter."""
    result = subprocess.run(
        ["ffmpeg", "-filters"],
        capture_output=True, text=True,
    )
    return "subtitles" in result.stdout


# ---------------------------------------------------------------------------
# Face-based crop
# ---------------------------------------------------------------------------

def _sample_frames_from_video(video_path: Path, start: float, end: float, n: int) -> list:
    """Extract n evenly-spaced frames from [start, end] via ffmpeg → in-memory PNG."""
    duration = end - start
    step = duration / (n + 1)
    frames = []
    for i in range(1, n + 1):
        t = start + i * step
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{t:.3f}",
                "-i", str(video_path),
                "-vframes", "1",
                "-f", "image2pipe", "-vcodec", "png", "pipe:1",
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            arr = np.frombuffer(result.stdout, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                frames.append(img)
    return frames


def _detect_face_center_x(video_path: Path, start: float, end: float, frame_w: int) -> int:
    """Return the area-weighted face centre-x across sampled frames.

    Samples _SAMPLE_FRAMES frames directly from the clip range, runs both
    frontal and profile Haar cascades, and weights each detected face centre
    by its pixel area so the largest (closest) face dominates.
    Falls back to centre crop when no faces are found.
    """
    frontal = cv2.CascadeClassifier(_CASCADE_FRONTAL)
    profile = cv2.CascadeClassifier(_CASCADE_PROFILE)

    frames = _sample_frames_from_video(video_path, start, end, _SAMPLE_FRAMES)

    weighted_sum = 0.0
    total_area = 0.0

    for img in frames:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Equalise histogram to improve detection in varied lighting
        gray = cv2.equalizeHist(gray)
        h_img = img.shape[0]
        for cascade in (frontal, profile):
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.05,
                minNeighbors=5,
                minSize=(max(30, frame_w // 20), max(30, h_img // 20)),
            )
            for (x, y, w, h) in faces:
                cx = x + w // 2
                area = float(w * h)
                weighted_sum += cx * area
                total_area += area

    if total_area > 0:
        return int(weighted_sum / total_area)
    return frame_w // 2  # fallback: centre crop


def _compute_crop(frame_w: int, frame_h: int, cx: int) -> tuple[int, int, int, int]:
    """Return (crop_x, crop_y, crop_w, crop_h) for a 9:16 crop centred on cx."""
    crop_w = int(frame_h * 9 / 16)
    crop_w = min(crop_w, frame_w)
    # Ensure even
    if crop_w % 2:
        crop_w -= 1

    crop_x = cx - crop_w // 2
    # Clamp to frame bounds
    crop_x = max(0, min(crop_x, frame_w - crop_w))
    if crop_x % 2:
        crop_x += 1

    return crop_x, 0, crop_w, frame_h


# ---------------------------------------------------------------------------
# SRT generation
# ---------------------------------------------------------------------------

def _seconds_to_srt_ts(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")


def generate_srt(
    transcript_segments: list[dict],
    clip_start: float,
    clip_end: float,
    out_path: Path,
) -> Path:
    """Write an SRT file with timestamps relative to clip_start."""
    clip_segs = [
        s for s in transcript_segments
        if s["end_time"] > clip_start and s["start_time"] < clip_end
    ]
    with out_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(clip_segs, start=1):
            t_start = max(0.0, seg["start_time"] - clip_start)
            t_end = min(clip_end - clip_start, seg["end_time"] - clip_start)
            f.write(f"{i}\n")
            f.write(f"{_seconds_to_srt_ts(t_start)} --> {_seconds_to_srt_ts(t_end)}\n")
            f.write(f"{seg['text'].strip()}\n\n")
    return out_path


# ---------------------------------------------------------------------------
# ffmpeg probe helpers
# ---------------------------------------------------------------------------

def _probe_dimensions(video_path: Path) -> tuple[int, int]:
    """Return (width, height) of the first video stream."""
    import json
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            return s["width"], s["height"]
    raise RuntimeError(f"No video stream found in {video_path}")


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def export_clip(
    video_id: uuid.UUID,
    candidate_id: uuid.UUID,
    start_time: float,
    end_time: float,
    transcript_segments: list[dict],
    storage_root: Path,
    variant_type: str = "export",
) -> dict:
    """Produce a 9:16 MP4 with burned-in subtitles.

    Returns a dict with file_path, srt_path, resolution.
    """
    video_path = storage_root / "videos" / str(video_id) / "normalized.mp4"

    out_dir = storage_root / "exports" / str(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{candidate_id}.mp4"
    srt_path = out_dir / f"{candidate_id}.srt"

    duration = end_time - start_time

    # 1. Probe source dimensions
    frame_w, frame_h = _probe_dimensions(video_path)

    # 2. Compute crop — sample frames directly from the clip for accurate face centering
    cx = _detect_face_center_x(video_path, start_time, end_time, frame_w)
    crop_x, crop_y, crop_w, crop_h = _compute_crop(frame_w, frame_h, cx)

    # 3. Generate SRT
    generate_srt(transcript_segments, start_time, end_time, srt_path)

    # 4. Build ffmpeg filter chain: crop → scale → (optional) burn subtitles
    vf_parts = [
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
        f"scale={_TARGET_W}:{_TARGET_H}:flags=lanczos",
    ]
    if _has_libass():
        srt_escaped = str(srt_path).replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        vf_parts.append(
            f"subtitles='{srt_escaped}':force_style='PlayResX=1080,PlayResY=1920,FontSize=42,Bold=1,Outline=2,Shadow=1,Alignment=2,MarginV=60'"
        )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", ",".join(vf_parts),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg export failed:\n{result.stderr[-2000:]}")

    return {
        "file_path": str(out_path),
        "subtitle_path": str(srt_path),
        "resolution": f"{_TARGET_W}x{_TARGET_H}",
    }


def export_preview(
    video_id: uuid.UUID,
    candidate_id: uuid.UUID,
    start_time: float,
    end_time: float,
    storage_root: Path,
) -> dict:
    """Produce a low-res 480x854 preview MP4 (no subtitles) for fast UI display."""
    video_path = storage_root / "videos" / str(video_id) / "normalized.mp4"

    out_dir = storage_root / "previews" / str(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{candidate_id}_preview.mp4"

    duration = end_time - start_time
    frame_w, frame_h = _probe_dimensions(video_path)
    cx = _detect_face_center_x(video_path, start_time, end_time, frame_w)
    crop_x, crop_y, crop_w, crop_h = _compute_crop(frame_w, frame_h, cx)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=480:854:flags=lanczos",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg preview failed:\n{result.stderr[-2000:]}")

    return {"file_path": str(out_path), "resolution": "480x854"}
