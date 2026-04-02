import uuid
from pathlib import Path

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

from services.storage import video_dir


def run_shot_detection(video_id: uuid.UUID, video_path: Path) -> list[dict]:
    """Detect shot boundaries in a video using PySceneDetect.

    Extracts one keyframe per shot and saves it under
    /storage/videos/{video_id}/keyframes/shot_{i:04d}.jpg.

    Returns a list of shot dicts with shot_index, start_time, end_time,
    start_frame, end_frame, keyframe_path.
    """
    keyframes_dir = video_dir(video_id) / "keyframes"
    keyframes_dir.mkdir(exist_ok=True)

    video = open_video(str(video_path))
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=27.0))
    manager.detect_scenes(video, show_progress=False)
    scenes = manager.get_scene_list()

    shots = []
    for i, (start, end) in enumerate(scenes):
        keyframe_path = _extract_keyframe(video_path, start.get_seconds(), i, keyframes_dir)
        shots.append({
            "shot_index": i,
            "start_time": round(start.get_seconds(), 3),
            "end_time": round(end.get_seconds(), 3),
            "start_frame": start.get_frames(),
            "end_frame": end.get_frames(),
            "keyframe_path": str(keyframe_path) if keyframe_path else None,
        })

    return shots


def _extract_keyframe(video_path: Path, timestamp: float, shot_index: int, out_dir: Path) -> Path | None:
    """Extract a single frame at timestamp using fast input-side seeking.

    Placing -ss before -i makes ffmpeg jump to the nearest GOP keyframe and
    decode only a few frames to reach the target — no full-video decode needed.
    """
    import subprocess

    out_path = out_dir / f"shot_{shot_index:04d}.jpg"
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{timestamp:.3f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "3",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        return None
    return out_path
