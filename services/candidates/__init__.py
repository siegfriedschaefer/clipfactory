from services.segmentation import _detect_rhetorical_trigger

TARGET_DURATIONS = [15, 20, 25, 30, 40, 45, 60]  # seconds to try per seed
MIN_DURATION = 13.0
MAX_DURATION = 62.0
DEDUP_OVERLAP_THRESHOLD = 0.75  # remove candidate if >75% overlaps with a kept one

TRIGGER_TO_TYPE = {
    "problem_intro": "mistake_to_fix",
    "contrast":      "contrarian_snippet",
    "controversy":   "contrarian_snippet",
    "statistic":     "quick_lesson",
    "warning":       "mistake_to_fix",
    "payoff":        "hook_to_payoff",
    "rhetorical":    "hook_to_payoff",
    "pause":         "claim_to_explanation",
    "shot_aligned":  "claim_to_explanation",
    "start":         "quick_lesson",
}


def _classify(trigger_marker: str | None, first_text: str) -> str:
    if trigger_marker and trigger_marker in TRIGGER_TO_TYPE:
        return TRIGGER_TO_TYPE[trigger_marker]
    detected = _detect_rhetorical_trigger(first_text)
    if detected and detected in TRIGGER_TO_TYPE:
        return TRIGGER_TO_TYPE[detected]
    return "quick_lesson"


def _overlap_ratio(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return overlap / shorter if shorter > 0 else 0.0


def run_candidate_generation(
    transcript_segments: list[dict],
    semantic_segments: list[dict],
) -> list[dict]:
    """Generate 30–100 clip candidates from transcript and semantic segments.

    For each semantic segment boundary (plus any rhetorical trigger positions
    not already covered), we try multiple window sizes (15–60s) and snap the
    end to a clean transcript segment boundary. Heavily overlapping candidates
    are deduplicated, keeping the one closest to 30s.

    Returns list of dicts: candidate_index, start_time, end_time, duration,
    candidate_type, trigger_marker, transcript_preview.
    """
    if not transcript_segments or not semantic_segments:
        return []

    t_segs = sorted(transcript_segments, key=lambda s: s["start_time"])

    def first_tseg_idx_at_or_after(t: float) -> int | None:
        for i, s in enumerate(t_segs):
            if s["start_time"] >= t - 0.5:
                return i
        return None

    # Seed points: (start_time, trigger_marker)
    seed_points: list[tuple[float, str | None]] = []

    # 1. Semantic segment boundaries
    for sem in semantic_segments:
        seed_points.append((sem["start_time"], sem["trigger_type"]))

    # 2. Every transcript segment containing a rhetorical trigger
    sem_times = {s["start_time"] for s in semantic_segments}
    for tseg in t_segs:
        trigger = _detect_rhetorical_trigger(tseg["text"])
        if trigger and tseg["start_time"] not in sem_times:
            seed_points.append((tseg["start_time"], trigger))

    # 3. Sliding window: every 5th transcript segment as additional seed
    #    so we get broad coverage even in long segments without many triggers
    covered = {t for t, _ in seed_points}
    for i in range(0, len(t_segs), 5):
        t = t_segs[i]["start_time"]
        if t not in covered:
            seed_points.append((t, None))

    # Generate raw candidates
    raw: list[dict] = []

    for seed_time, trigger_marker in seed_points:
        start_idx = first_tseg_idx_at_or_after(seed_time)
        if start_idx is None:
            continue

        actual_start = t_segs[start_idx]["start_time"]

        for target_dur in TARGET_DURATIONS:
            target_end = actual_start + target_dur

            # Find transcript segment end closest to target_end within [MIN, MAX]
            best_idx = None
            for j in range(start_idx, len(t_segs)):
                seg_end = t_segs[j]["end_time"]
                if seg_end < actual_start + MIN_DURATION:
                    continue
                if seg_end > actual_start + MAX_DURATION:
                    break
                if best_idx is None or abs(seg_end - target_end) < abs(t_segs[best_idx]["end_time"] - target_end):
                    best_idx = j

            if best_idx is None:
                continue

            actual_end = t_segs[best_idx]["end_time"]
            duration = round(actual_end - actual_start, 3)

            texts = [s["text"] for s in t_segs[start_idx: best_idx + 1]]
            preview = " ".join(texts)[:200]
            candidate_type = _classify(trigger_marker, t_segs[start_idx]["text"])

            raw.append({
                "start_time": round(actual_start, 3),
                "end_time": round(actual_end, 3),
                "duration": duration,
                "candidate_type": candidate_type,
                "trigger_marker": trigger_marker,
                "transcript_preview": preview,
            })

    # Deduplicate: sort by closeness to 30s (sweet spot), keep non-overlapping
    raw.sort(key=lambda c: abs(c["duration"] - 30))

    final: list[dict] = []
    for candidate in raw:
        if not any(
            _overlap_ratio(
                candidate["start_time"], candidate["end_time"],
                kept["start_time"], kept["end_time"],
            ) > DEDUP_OVERLAP_THRESHOLD
            for kept in final
        ):
            final.append(candidate)

    final.sort(key=lambda c: c["start_time"])
    for i, c in enumerate(final):
        c["candidate_index"] = i

    return final
