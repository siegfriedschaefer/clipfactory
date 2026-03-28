import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from moonshine_voice import Transcriber, load_wav_file, get_model_for_language

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def extract_audio_to_wav(video_path: Path, out_path: Path) -> None:
    """Extract audio from a video file to a 16kHz mono WAV using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-sample_fmt", "s16",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe audio/video with Moonshine")
    parser.add_argument("input", type=Path, help="Path to input file (WAV or video: mp4, mov, ...)")
    parser.add_argument("--model", default="base-en", help="Moonshine model name (e.g. tiny-en, base-en; default: base-en)")
    parser.add_argument("--output", type=Path, default=None, help="Save transcript to this file (.txt or .json)")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Error: input file not found: {args.input}")

    print(f"Downloading/loading Moonshine model '{args.model}'...")
    model_path, model_arch = get_model_for_language("en")
    transcriber = Transcriber(model_path, model_arch)

    if args.input.suffix.lower() in VIDEO_EXTENSIONS:
        print(f"Extracting audio from {args.input}...")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        extract_audio_to_wav(args.input, wav_path)
    else:
        wav_path = args.input

    print(f"Loading audio {wav_path}...")
    audio_data, sample_rate = load_wav_file(wav_path)

    print("Transcribing...")
    transcript = transcriber.transcribe_without_streaming(audio_data, sample_rate)
    result = "\n".join(line.text for line in transcript.lines)

    print("\n--- Transcript ---")
    print(result)

    if args.output:
        if args.output.suffix == ".json":
            args.output.write_text(json.dumps({"transcript": result}, indent=2, ensure_ascii=False))
        else:
            args.output.write_text(result)
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
