import re

from services.segmentation import _detect_rhetorical_trigger

# --- Stopwords (EN + DE, combined) -----------------------------------
STOPWORDS = {
    # EN
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it", "they",
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "that",
    "this", "these", "those", "what", "which", "who", "when", "where",
    "how", "if", "then", "than", "so", "just", "not", "no", "up", "out",
    "about", "into", "very", "also", "there", "their", "them", "its",
    "um", "uh", "ah", "yeah", "yes",
    # DE
    "ich", "du", "er", "sie", "es", "wir", "ihr", "die", "der", "das",
    "ein", "eine", "und", "oder", "aber", "in", "an", "auf", "zu", "für",
    "von", "mit", "bei", "nach", "ist", "war", "sind", "waren", "hat",
    "haben", "wird", "würde", "kann", "nicht", "auch", "noch", "schon",
    "wenn", "dann", "dass", "was", "wie", "so", "ja", "nein", "äh", "ähm",
}

# Filler words that hurt quality
FILLER_WORDS = {
    "um", "uh", "ah", "like", "you know", "i mean", "basically", "literally",
    "actually", "honestly", "right", "okay", "so", "well",
    "äh", "ähm", "also", "halt", "eigentlich", "sozusagen",
}

# Actionability patterns
ACTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(do|try|use|start|stop|avoid|make sure|remember|focus|build|create|learn|take)\b",
        r"\b(you (should|need to|have to|must|can))\b",
        r"\b(here'?s? how)\b",
        r"\b(step \d+|first|second|third|next step)\b",
    ]
]

# Curiosity gap patterns
CURIOSITY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\?",
        r"\b(you won'?t believe|the secret|nobody knows|hidden|surprising|shocking)\b",
        r"\b(here'?s? why|the reason|turns out|it turns out)\b",
        r"\b(what (most|nobody|no one))\b",
    ]
]

# Controversy / contrast markers (subset)
CONTROVERSY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(but the truth|the reality is|actually|however|on the other hand)\b",
        r"\b(most people (think|believe|don'?t|never))\b",
        r"\b(nobody talks|no one tells|they don'?t want)\b",
        r"\b(aber die wahrheit|im gegensatz|niemand spricht)\b",
    ]
]

# Configurable niche keywords (extend as needed)
NICHE_KEYWORDS: list[str] = [
    "ai", "gpu", "nvidia", "chips", "semiconductor", "llm", "model",
    "infrastructure", "data center", "computing", "algorithm",
    "startup", "founder", "ceo", "revenue", "valuation",
]
_NICHE_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in NICHE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b\d+([.,]\d+)?\b")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZäöüÄÖÜß]+", text.lower())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def compute_text_features(
    candidate: dict,
    transcript_segments: list[dict],
) -> dict[str, float]:
    """Compute all text-based features for a single clip candidate.

    Args:
        candidate:  dict with start_time, end_time, duration
        transcript_segments: all transcript segments for the video (sorted)

    Returns dict of feature_key → float value (all normalised to [0, 1]
    except duration which is in seconds).
    """
    start = candidate["start_time"]
    end = candidate["end_time"]
    duration = candidate["duration"]

    # Segments that fall within this candidate
    clip_segs = [
        s for s in transcript_segments
        if s["start_time"] >= start - 0.1 and s["end_time"] <= end + 0.1
    ]
    if not clip_segs:
        return {k: 0.0 for k in _all_keys(duration)}

    full_text = " ".join(s["text"] for s in clip_segs)
    first_seg = clip_segs[0]
    first_text = first_seg["text"]

    # Segments in first 3 seconds
    first_3s_text = " ".join(
        s["text"] for s in clip_segs
        if s["start_time"] < start + 3.0
    )

    words = _words(full_text)
    sentences = _sentences(full_text)
    word_count = len(words) or 1
    sentence_count = len(sentences) or 1

    # hook_strength: rhetorical trigger or question in first segment
    hook_strength = 0.0
    if _detect_rhetorical_trigger(first_text):
        hook_strength = 1.0
    elif "?" in first_text:
        hook_strength = 0.6

    # hook_in_first_3s
    hook_in_first_3s = 1.0 if (
        _detect_rhetorical_trigger(first_3s_text) or "?" in first_3s_text
    ) else 0.0

    # curiosity_gap
    curiosity_gap = min(1.0, sum(
        1 for p in CURIOSITY_PATTERNS if p.search(full_text)
    ) / len(CURIOSITY_PATTERNS))

    # number_density: numbers per second
    number_count = len(_NUMBER_RE.findall(full_text))
    number_density = min(1.0, number_count / (duration / 10))  # normalise: 1/10s = 1.0

    # clarity: shorter avg sentence = clearer (invert: 1 = very clear)
    avg_words_per_sentence = word_count / sentence_count
    clarity = max(0.0, 1.0 - (avg_words_per_sentence - 5) / 25)  # 5w=1.0, 30w=0.0

    # information_density: non-stopword ratio
    content_words = [w for w in words if w not in STOPWORDS]
    information_density = len(content_words) / word_count

    # novelty_proxy: long uncommon words not in stopwords
    novel_words = [w for w in content_words if len(w) > 7]
    novelty_proxy = min(1.0, len(novel_words) / (word_count / 5))

    # controversy_proxy
    controversy_proxy = min(1.0, sum(
        1 for p in CONTROVERSY_PATTERNS if p.search(full_text)
    ) / len(CONTROVERSY_PATTERNS) * 2)

    # actionability
    actionability = min(1.0, sum(
        1 for p in ACTION_PATTERNS if p.search(full_text)
    ) / len(ACTION_PATTERNS) * 2)

    # niche_keywords per second
    niche_count = len(_NICHE_RE.findall(full_text))
    niche_keywords = min(1.0, niche_count / (duration / 15))

    return {
        "hook_strength":      round(hook_strength, 4),
        "hook_in_first_3s":   round(hook_in_first_3s, 4),
        "curiosity_gap":      round(curiosity_gap, 4),
        "number_density":     round(number_density, 4),
        "clarity":            round(max(0.0, min(1.0, clarity)), 4),
        "information_density": round(information_density, 4),
        "novelty_proxy":      round(novelty_proxy, 4),
        "controversy_proxy":  round(controversy_proxy, 4),
        "actionability":      round(actionability, 4),
        "niche_keywords":     round(niche_keywords, 4),
        "duration":           round(duration, 3),
    }


def _all_keys(duration: float) -> dict[str, float]:
    return {
        "hook_strength": 0.0, "hook_in_first_3s": 0.0,
        "curiosity_gap": 0.0, "number_density": 0.0,
        "clarity": 0.0, "information_density": 0.0,
        "novelty_proxy": 0.0, "controversy_proxy": 0.0,
        "actionability": 0.0, "niche_keywords": 0.0,
        "duration": duration,
    }
