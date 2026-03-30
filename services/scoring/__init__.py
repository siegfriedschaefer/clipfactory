"""Specialist score computation for clip candidates.

Each score is a weighted sum of normalised features (all inputs in [0, 1]).
Outputs are also in [0, 1].
"""

# ---------------------------------------------------------------------------
# Weights — tunable via config in a future iteration
# ---------------------------------------------------------------------------

_HOOK_WEIGHTS = {
    "hook_strength":   0.35,
    "hook_in_first_3s": 0.30,
    "opening_energy":  0.20,
    "curiosity_gap":   0.15,
}

# speech_rate for retention: penalise extremes (too slow or too fast).
# We compute a bell-shaped factor separately and inject it.
_RETENTION_WEIGHTS = {
    "information_density": 0.35,
    "clarity":             0.30,
    "_speech_rate_bell":   0.20,  # derived below
    "_pause_penalty":      0.15,  # 1 - pause_ratio
}

_SHARE_WEIGHTS = {
    "controversy_proxy": 0.30,
    "novelty_proxy":     0.25,
    "actionability":     0.30,
    "number_density":    0.15,
}

_PACKAGING_WEIGHTS = {
    "cropability_9_16": 0.40,
    "face_visible":     0.35,
    "shot_count":       0.15,
    "ocr_text_present": 0.10,
}

# risk_score: higher = riskier (will be subtracted in meta-rank)
_RISK_WEIGHTS = {
    "filler_word_density": 0.50,
    "_pause_penalty":      0.30,  # pause_ratio (high pauses = bad)
    "_clarity_inv":        0.20,  # 1 - clarity
}


def _w(features: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted sum; skip sentinel keys starting with '_'."""
    total = sum(features.get(k, 0.0) * w for k, w in weights.items() if not k.startswith("_"))
    return round(min(1.0, max(0.0, total)), 4)


def compute_specialist_scores(features: dict[str, float]) -> dict[str, float]:
    """Compute 5 specialist scores from a flat feature dict.

    Args:
        features: merged dict of all feature_key → value for one candidate
                  (text + audio + video features combined)

    Returns dict with hook_score, retention_score, share_score,
    packaging_score, risk_score — all in [0, 1].
    """
    pause_ratio = features.get("pause_ratio", 0.0)
    clarity = features.get("clarity", 0.0)
    speech_rate = features.get("speech_rate", 0.0)

    # Bell curve for speech_rate: peaks at 0.6 (≈ 1.8 wps), drops off at extremes
    speech_rate_bell = max(0.0, 1.0 - abs(speech_rate - 0.6) / 0.6)

    # --- hook_score ---
    hook_score = _w(features, _HOOK_WEIGHTS)

    # --- retention_score ---
    retention_score = round(min(1.0, max(0.0,
        features.get("information_density", 0.0) * 0.35
        + clarity * 0.30
        + speech_rate_bell * 0.20
        + (1.0 - pause_ratio) * 0.15
    )), 4)

    # --- share_score ---
    share_score = _w(features, _SHARE_WEIGHTS)

    # --- packaging_score ---
    packaging_score = _w(features, _PACKAGING_WEIGHTS)

    # --- risk_score ---
    risk_score = round(min(1.0, max(0.0,
        features.get("filler_word_density", 0.0) * 0.50
        + pause_ratio * 0.30
        + (1.0 - clarity) * 0.20
    )), 4)

    return {
        "hook_score":       hook_score,
        "retention_score":  retention_score,
        "share_score":      share_score,
        "packaging_score":  packaging_score,
        "risk_score":       risk_score,
    }


# ---------------------------------------------------------------------------
# Meta-ranker weights (from week3.yaml)
# ---------------------------------------------------------------------------

_VIRAL_WEIGHTS = {
    "hook_score":       0.35,
    "retention_score":  0.25,
    "share_score":      0.20,
    "packaging_score":  0.15,
    "risk_score":      -0.05,
}


def compute_viral_score(scores: dict[str, float]) -> float:
    """Combine specialist scores into a single viral_score in [0, 1]."""
    raw = sum(scores.get(k, 0.0) * w for k, w in _VIRAL_WEIGHTS.items())
    return round(min(1.0, max(0.0, raw)), 4)


# ---------------------------------------------------------------------------
# Reason tag generation (w3-t6)
# ---------------------------------------------------------------------------

def generate_reasons(scores: dict[str, float], features: dict[str, float]) -> list[str]:
    """Derive 3–5 human-readable reason tags from scores and features."""
    tags: list[tuple[float, str]] = []  # (signal_strength, tag)

    if scores.get("hook_score", 0.0) >= 0.6:
        tags.append((scores["hook_score"], "starker Einstieg"))

    if features.get("hook_in_first_3s", 0.0) >= 0.5:
        tags.append((features["hook_in_first_3s"], "rhetorischer Trigger in ersten 3 Sekunden"))

    if features.get("opening_energy", 0.0) >= 0.5:
        tags.append((features["opening_energy"], "hohe Sprecher-Energie am Anfang"))

    if features.get("information_density", 0.0) >= 0.55:
        tags.append((features["information_density"], "hohe Informationsdichte"))

    if features.get("actionability", 0.0) >= 0.45:
        tags.append((features["actionability"], "konkreter Tipp / Handlungsempfehlung"))

    if features.get("controversy_proxy", 0.0) >= 0.35:
        tags.append((features["controversy_proxy"], "kontroverse Aussage"))

    if features.get("clarity", 0.0) >= 0.6 and features.get("duration", 60.0) <= 35.0:
        tags.append((features["clarity"], "kurze klare Struktur"))

    if scores.get("packaging_score", 0.0) >= 0.6:
        tags.append((scores["packaging_score"], "gute Cropbarkeit"))

    if features.get("number_density", 0.0) >= 0.3:
        tags.append((features["number_density"], "konkrete Zahlen / Statistiken"))

    if features.get("novelty_proxy", 0.0) >= 0.4:
        tags.append((features["novelty_proxy"], "ungewöhnlicher Sprachstil"))

    # Sort by signal strength descending, return top 3–5
    tags.sort(key=lambda t: t[0], reverse=True)
    selected = [tag for _, tag in tags[:5]]

    # Always return at least 3 tags, padding with the next best if needed
    if len(selected) < 3 and len(tags) >= 3:
        selected = [tag for _, tag in tags[:3]]
    elif len(selected) < 1:
        selected = ["kein klares Stärken-Signal"]

    return selected


# ---------------------------------------------------------------------------
# Full ranking pass over all candidates for one video
# ---------------------------------------------------------------------------

def rank_candidates(
    candidates: list[dict],
) -> list[dict]:
    """Compute viral_score, rank, and reasons for all candidates of a video.

    Args:
        candidates: list of dicts, each with:
            - candidate_id (any hashable)
            - scores: dict from compute_specialist_scores()
            - features: flat feature dict

    Returns same list enriched with viral_score, rank, reasons — sorted by rank.
    """
    for c in candidates:
        c["viral_score"] = compute_viral_score(c["scores"])
        c["reasons"] = generate_reasons(c["scores"], c["features"])

    # Sort descending by viral_score; stable sort preserves order on ties
    ranked = sorted(candidates, key=lambda c: c["viral_score"], reverse=True)
    for i, c in enumerate(ranked, start=1):
        c["rank"] = i

    return ranked
