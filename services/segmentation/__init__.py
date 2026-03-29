import re

PAUSE_THRESHOLD = 1.5       # seconds — gap between transcript segments
SHOT_ALIGN_WINDOW = 3.0     # seconds — nudge boundary to nearest shot cut if within this
MIN_SEGMENT_DURATION = 10.0 # seconds — merge segments shorter than this into the next

# Rhetorical markers for DE + EN, grouped by type
RHETORICAL_MARKERS: dict[str, list[str]] = {
    "problem_intro": [
        r"die meisten machen fehler", r"das größte problem ist", r"das problem ist",
        r"most people", r"the biggest problem", r"the problem is", r"here's the problem",
    ],
    "contrast": [
        r"aber die wahrheit ist", r"im gegensatz dazu",
        r"but the truth is", r"but here's the thing", r"the reality is",
        r"on the other hand", r"however,", r"yet,",
    ],
    "statistic": [
        r"\d+\s*%", r"in einer studie", r"in a study", r"research shows",
        r"according to", r"\d+ (million|billion|thousand)",
    ],
    "warning": [
        r"pass auf", r"das ist gefährlich", r"vorsicht",
        r"be careful", r"watch out", r"don't do this", r"stop doing",
    ],
    "controversy": [
        r"niemand spricht darüber", r"das will dir keiner sagen",
        r"nobody talks about", r"no one tells you", r"nobody tells you",
        r"they don't want you to know",
    ],
    "payoff": [
        r"am ende wirst du", r"das ergebnis war", r"deswegen funktioniert",
        r"the result was", r"that's why", r"the way i deal with",
        r"here's how", r"this is how", r"so here's what",
    ],
}

# Compiled once at import time
_COMPILED: list[tuple[str, re.Pattern]] = [
    (marker_type, re.compile(pattern, re.IGNORECASE))
    for marker_type, patterns in RHETORICAL_MARKERS.items()
    for pattern in patterns
]


def _detect_rhetorical_trigger(text: str) -> str | None:
    """Return the first matching marker type, or None."""
    for marker_type, pattern in _COMPILED:
        if pattern.search(text):
            return marker_type
    return None


def _nearest_shot_time(t: float, shots: list[dict], window: float) -> float | None:
    """Return the start_time of the nearest shot boundary within window, or None."""
    best = None
    best_dist = window
    for shot in shots:
        dist = abs(shot["start_time"] - t)
        if dist < best_dist:
            best_dist = dist
            best = shot["start_time"]
    return best


def run_segmentation(
    transcript_segments: list[dict],
    shots: list[dict],
) -> list[dict]:
    """Segment transcript into semantic chunks.

    Steps:
      1. Find pause boundaries (gap > PAUSE_THRESHOLD between consecutive segments)
      2. Find rhetorical trigger boundaries (marker at start of a segment)
      3. Merge boundary set, shot-align each boundary
      4. Build semantic segments from boundary points
      5. Merge segments shorter than MIN_SEGMENT_DURATION

    Returns list of dicts: segment_index, start_time, end_time,
    trigger_type, transcript_preview.
    """
    if not transcript_segments:
        return []

    segs = sorted(transcript_segments, key=lambda s: s["start_time"])

    # --- Step 1 & 2: collect boundary time points with their trigger type ---
    # Map: start_time → trigger_type (later trigger wins if multiple)
    boundaries: dict[float, str] = {}

    for i in range(1, len(segs)):
        prev, curr = segs[i - 1], segs[i]

        gap = curr["start_time"] - prev["end_time"]
        if gap >= PAUSE_THRESHOLD:
            boundaries[curr["start_time"]] = "pause"

        trigger = _detect_rhetorical_trigger(curr["text"])
        if trigger:
            boundaries[curr["start_time"]] = "rhetorical"

    # --- Step 3: shot-align each boundary ---
    aligned: dict[float, str] = {}
    for t, trigger in boundaries.items():
        snapped = _nearest_shot_time(t, shots, SHOT_ALIGN_WINDOW)
        aligned_t = snapped if snapped is not None else t
        trigger_final = "shot_aligned" if snapped is not None else trigger
        aligned[aligned_t] = trigger_final

    # Always include the very start
    boundary_times = sorted({segs[0]["start_time"]} | set(aligned.keys()))

    # --- Step 4: build semantic segments from boundary points ---
    raw_segments = []
    end_time_of_last = segs[-1]["end_time"]

    for i, start in enumerate(boundary_times):
        end = boundary_times[i + 1] if i + 1 < len(boundary_times) else end_time_of_last
        trigger = aligned.get(start, "pause") if i > 0 else "start"

        # Collect transcript text for this window
        texts = [
            s["text"] for s in segs
            if s["start_time"] >= start and s["end_time"] <= end + 0.1
        ]
        preview = " ".join(texts)[:200] if texts else ""

        raw_segments.append({
            "start_time": round(start, 3),
            "end_time": round(end, 3),
            "trigger_type": trigger,
            "transcript_preview": preview,
        })

    # --- Step 5: merge segments shorter than MIN_SEGMENT_DURATION ---
    merged = []
    for seg in raw_segments:
        duration = seg["end_time"] - seg["start_time"]
        if merged and duration < MIN_SEGMENT_DURATION:
            # absorb into previous segment
            merged[-1]["end_time"] = seg["end_time"]
            merged[-1]["transcript_preview"] = (
                merged[-1]["transcript_preview"] + " " + seg["transcript_preview"]
            )[:200]
        else:
            merged.append(seg)

    # Add segment_index
    for i, seg in enumerate(merged):
        seg["segment_index"] = i

    return merged
