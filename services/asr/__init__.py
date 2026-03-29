import json
import uuid
from pathlib import Path

from moonshine_voice import Transcriber, get_model_for_language, load_wav_file

from services.storage import video_dir


def run_asr(video_id: uuid.UUID, audio_path: Path) -> list[dict]:
    """Transcribe audio using Moonshine.

    Saves transcript.json to /storage/videos/{video_id}/transcript.json and
    returns a list of segment dicts with segment_index, start_time, end_time,
    text, and words (None — Moonshine does not provide word timestamps in
    non-streaming mode).
    """
    model_path, model_arch = get_model_for_language("en")
    transcriber = Transcriber(model_path, model_arch)

    audio_data, sample_rate = load_wav_file(str(audio_path))
    transcript = transcriber.transcribe_without_streaming(audio_data, sample_rate)

    segments = []
    for i, line in enumerate(transcript.lines):
        segments.append({
            "segment_index": i,
            "start_time": round(line.start_time, 3),
            "end_time": round(line.start_time + line.duration, 3),
            "text": line.text,
            "words": (
                [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "confidence": w.confidence,
                    }
                    for w in line.words
                ]
                if line.words else None
            ),
        })

    out_path = video_dir(video_id) / "transcript.json"
    out_path.write_text(
        json.dumps({"segments": segments}, indent=2, ensure_ascii=False)
    )

    return segments
