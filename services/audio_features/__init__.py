"""Audio feature extraction for clip candidates.

Uses scipy for signal processing (no extra dep beyond numpy).
speech_rate is derived from transcript segment timestamps.
"""
import wave
from pathlib import Path

import numpy as np

# Filler words (kept in sync with text features module)
_FILLER_WORDS = {
    "um", "uh", "ah", "like", "basically", "literally",
    "actually", "honestly", "okay", "well",
    "äh", "ähm", "also", "halt", "eigentlich", "sozusagen",
}


def _load_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    """Load WAV file as float32 mono array, return (samples, sample_rate)."""
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    dtype = dtype_map.get(sampwidth, np.int16)
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    # Normalise to [-1, 1]
    max_val = float(np.iinfo(dtype).max)
    samples = samples / max_val
    return samples, sample_rate


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples ** 2)))


def _frame_rms(samples: np.ndarray, sample_rate: int, frame_ms: int = 30) -> np.ndarray:
    """Compute RMS energy per frame."""
    frame_len = int(sample_rate * frame_ms / 1000)
    if frame_len == 0 or len(samples) == 0:
        return np.array([])
    n_frames = len(samples) // frame_len
    frames = samples[: n_frames * frame_len].reshape(n_frames, frame_len)
    return np.sqrt(np.mean(frames ** 2, axis=1))


def compute_audio_features(
    candidate: dict,
    transcript_segments: list[dict],
    audio_path: Path,
) -> dict[str, float]:
    """Compute audio-based features for a single clip candidate.

    Args:
        candidate: dict with start_time, end_time, duration
        transcript_segments: all transcript segments for the video (sorted)
        audio_path: path to the video's audio.wav

    Returns dict of feature_key → float (all normalised to [0, 1] where applicable).
    """
    start = candidate["start_time"]
    end = candidate["end_time"]
    duration = candidate["duration"]

    zeros = {
        "loudness_mean": 0.0,
        "loudness_dynamics": 0.0,
        "pause_ratio": 0.0,
        "speech_rate": 0.0,
        "opening_energy": 0.0,
        "filler_word_density": 0.0,
    }

    if not audio_path.exists() or duration <= 0:
        return zeros

    try:
        all_samples, sr = _load_wav_mono(audio_path)
    except Exception:
        return zeros

    # Slice samples for this clip
    s_start = int(start * sr)
    s_end = int(end * sr)
    clip_samples = all_samples[s_start:s_end]

    if len(clip_samples) == 0:
        return zeros

    frame_energies = _frame_rms(clip_samples, sr, frame_ms=30)

    if len(frame_energies) == 0:
        return zeros

    # --- loudness_mean ---
    # Normalise: RMS of 0.3 considered "loud" (≈ -10 dBFS) → clamp at 1.0
    loudness_mean = min(1.0, float(np.mean(frame_energies)) / 0.3)

    # --- loudness_dynamics ---
    # Normalise: std of 0.1 considered "high dynamics"
    loudness_dynamics = min(1.0, float(np.std(frame_energies)) / 0.1)

    # --- pause_ratio ---
    # Frames below silence threshold
    silence_threshold = 0.01
    n_silent = int(np.sum(frame_energies < silence_threshold))
    pause_ratio = n_silent / len(frame_energies)

    # --- opening_energy ---
    # Mean RMS in first 3s relative to clip mean
    first_3s_samples = clip_samples[: int(3.0 * sr)]
    opening_rms = _rms(first_3s_samples)
    clip_rms = _rms(clip_samples)
    if clip_rms > 0:
        opening_energy = min(1.0, opening_rms / (clip_rms * 2))
    else:
        opening_energy = 0.0

    # --- speech_rate (from transcript timestamps) ---
    clip_segs = [
        s for s in transcript_segments
        if s["start_time"] >= start - 0.1 and s["end_time"] <= end + 0.1
    ]
    word_count = sum(len(s["text"].split()) for s in clip_segs)
    speech_duration = sum(s["end_time"] - s["start_time"] for s in clip_segs) or duration
    words_per_second = word_count / speech_duration if speech_duration > 0 else 0
    # Normalise: 3 wps ≈ fast but normal speech → 1.0; clamp at 1.0
    speech_rate = min(1.0, words_per_second / 3.0)

    # --- filler_word_density ---
    full_text = " ".join(s["text"] for s in clip_segs).lower()
    filler_count = sum(
        full_text.count(fw) for fw in _FILLER_WORDS
    )
    # Normalise: 1 filler/5s = 1.0 (high density)
    filler_word_density = min(1.0, filler_count / max(1.0, duration / 5.0))

    return {
        "loudness_mean":      round(loudness_mean, 4),
        "loudness_dynamics":  round(loudness_dynamics, 4),
        "pause_ratio":        round(pause_ratio, 4),
        "speech_rate":        round(speech_rate, 4),
        "opening_energy":     round(opening_energy, 4),
        "filler_word_density": round(filler_word_density, 4),
    }
