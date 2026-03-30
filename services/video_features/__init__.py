"""Video feature extraction for clip candidates.

Uses OpenCV (bundled with scenedetect). No additional dependencies.
- Haar cascade for face detection
- MSER for text region detection
- Frame-diff for visual dynamics
All keyframes were extracted during shot detection in the CPU worker.
"""
from pathlib import Path

import cv2
import numpy as np

# Lazy-loaded Haar cascade (loaded once per process)
_face_cascade: cv2.CascadeClassifier | None = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    global _face_cascade
    if _face_cascade is None:
        xml = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_cascade = cv2.CascadeClassifier(xml)
    return _face_cascade


def _detect_faces(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return list of (x, y, w, h) face bounding boxes."""
    cascade = _get_face_cascade()
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )
    if len(faces) == 0:
        return []
    return [tuple(f) for f in faces]


def _has_text_regions(gray: np.ndarray) -> bool:
    """Use MSER to detect text-like regions in frame."""
    mser = cv2.MSER_create(5, 60, 14400)
    regions, _ = mser.detectRegions(gray)
    # If enough compact regions are found, text is likely present
    return len(regions) > 20


def _frame_diff(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """Mean absolute pixel difference between two same-size gray frames, normalised to [0,1]."""
    if img_a.shape != img_b.shape:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
    diff = cv2.absdiff(img_a, img_b)
    return float(np.mean(diff)) / 255.0


def _load_keyframes_for_clip(
    keyframes_dir: Path,
    shots: list[dict],
    start: float,
    end: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Load (bgr, gray) pairs for keyframes whose shot overlaps with the clip."""
    result = []
    for i, shot in enumerate(shots):
        # Shot overlaps with clip if shot.start < clip.end and shot.end > clip.start
        if shot["end_time"] <= start or shot["start_time"] >= end:
            continue
        kf_path = keyframes_dir / f"shot_{i:04d}.jpg"
        if not kf_path.exists():
            continue
        bgr = cv2.imread(str(kf_path))
        if bgr is None:
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        result.append((bgr, gray))
    return result


def compute_video_features(
    candidate: dict,
    shots: list[dict],
    keyframes_dir: Path,
) -> dict[str, float]:
    """Compute video-based features for a single clip candidate.

    Args:
        candidate:      dict with start_time, end_time, duration
        shots:          list of dicts with start_time, end_time (ordered)
        keyframes_dir:  path to /storage/videos/{video_id}/keyframes/

    Returns dict of feature_key → float.
    """
    start = candidate["start_time"]
    end = candidate["end_time"]

    zeros = {
        "shot_count": 0.0,
        "face_visible": 0.0,
        "cropability_9_16": 0.0,
        "ocr_text_present": 0.0,
        "visual_dynamics": 0.0,
    }

    # --- shot_count ---
    clip_shots = [
        s for s in shots
        if s["end_time"] > start and s["start_time"] < end
    ]
    shot_count = len(clip_shots)
    # Normalise: 10 shots in a clip = 1.0 (fast-cut content)
    shot_count_norm = min(1.0, shot_count / 10.0)

    if not keyframes_dir.exists():
        return {**zeros, "shot_count": round(shot_count_norm, 4)}

    frames = _load_keyframes_for_clip(keyframes_dir, shots, start, end)

    if not frames:
        return {**zeros, "shot_count": round(shot_count_norm, 4)}

    # --- face detection across all keyframes ---
    all_face_boxes: list[tuple[int, int, int, int]] = []
    has_face = False
    frame_h, frame_w = frames[0][1].shape[:2]

    for bgr, gray in frames:
        boxes = _detect_faces(gray)
        if boxes:
            has_face = True
            all_face_boxes.extend(boxes)

    face_visible = 1.0 if has_face else 0.0

    # --- cropability_9_16 ---
    # A 9:16 crop takes the centre ~56% of the frame width.
    # Score = fraction of detected faces whose centre falls in the middle 60% of frame width.
    if has_face and all_face_boxes and frame_w > 0:
        centre_margin = 0.20  # 20% from each side
        left_bound = frame_w * centre_margin
        right_bound = frame_w * (1 - centre_margin)
        centred = sum(
            1 for (x, y, w, h) in all_face_boxes
            if left_bound <= (x + w / 2) <= right_bound
        )
        cropability_9_16 = centred / len(all_face_boxes)
    elif not has_face:
        # No face — check if frame is already portrait-like
        cropability_9_16 = 0.5 if frame_w < frame_h else 0.3
    else:
        cropability_9_16 = 0.0

    # --- ocr_text_present ---
    text_detected = any(_has_text_regions(gray) for _, gray in frames)
    ocr_text_present = 1.0 if text_detected else 0.0

    # --- visual_dynamics ---
    # Mean frame-to-frame difference across consecutive keyframes
    if len(frames) >= 2:
        diffs = [
            _frame_diff(frames[i][1], frames[i + 1][1])
            for i in range(len(frames) - 1)
        ]
        # Normalise: mean diff of 0.15 (15% pixel change) → 1.0
        visual_dynamics = min(1.0, float(np.mean(diffs)) / 0.15)
    else:
        visual_dynamics = 0.0

    return {
        "shot_count":       round(shot_count_norm, 4),
        "face_visible":     round(face_visible, 4),
        "cropability_9_16": round(cropability_9_16, 4),
        "ocr_text_present": round(ocr_text_present, 4),
        "visual_dynamics":  round(visual_dynamics, 4),
    }
