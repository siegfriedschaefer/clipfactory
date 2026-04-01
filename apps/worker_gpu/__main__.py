"""GPU Worker — processes ASR jobs from the Redis queue using Moonshine."""
import json
import logging
import uuid
from pathlib import Path

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import settings
from sqlalchemy import select

from apps.api.models import ClipCandidate, ClipFeature, ClipScore, Job, JobStatus, SemanticSegment, Shot, TranscriptSegment, Video
from services.asr import run_asr
from services.ingestion import CHUNK_DURATION
from services.audio_features import compute_audio_features
from services.candidates import run_candidate_generation
from services.features import compute_text_features
from services.jobs import transition
from services.logging_config import setup
from services.scoring import compute_specialist_scores, rank_candidates
from services.segmentation import run_segmentation
from services.video_features import compute_video_features

setup()
logger = logging.getLogger(__name__)

QUEUE_IN = "queue:asr"
QUEUE_INGESTION = "queue:ingestion"
MAX_RETRIES = 3


def process(payload: dict, session: Session) -> None:
    job_id = uuid.UUID(payload["job_id"])
    video_id = uuid.UUID(payload["video_id"])

    job = session.get(Job, job_id)
    video = session.get(Video, video_id)

    if job is None or video is None:
        logger.error("Job or video not found — skipping", extra={"job_id": str(job_id), "video_id": str(video_id)})
        return

    # Guard: skip duplicate messages
    if job.status not in (JobStatus.ready_for_asr, JobStatus.failed):
        logger.warning("Job %s already in status %s — skipping", job_id, job.status)
        return

    # Determine audio source: chunked (> 15 min) or single file
    video_storage = Path(settings.storage_root) / "videos" / str(video_id)
    chunks_dir = video_storage / "audio_chunks"
    audio_path = video_storage / "audio.wav"

    if chunks_dir.exists():
        chunk_paths = sorted(chunks_dir.glob("chunk_*.wav"))
        if not chunk_paths:
            raise FileNotFoundError(f"audio_chunks/ exists but contains no WAV files: {chunks_dir}")
    elif audio_path.exists():
        chunk_paths = []
    else:
        raise FileNotFoundError(f"No audio found for video {video_id} (checked audio.wav and audio_chunks/)")

    transition(job, JobStatus.transcribing)
    video.status = "transcribing"
    session.commit()

    if chunk_paths:
        logger.info("Transcribing video %s in %d chunks", video_id, len(chunk_paths))
        segments = []
        global_index = 0
        for i, chunk_path in enumerate(chunk_paths):
            offset = i * CHUNK_DURATION
            logger.info("  chunk %d/%d (offset %.0fs): %s", i + 1, len(chunk_paths), offset, chunk_path.name)
            chunk_segs = run_asr(video_id, chunk_path)
            for seg in chunk_segs:
                seg["start_time"] += offset
                seg["end_time"] += offset
                seg["segment_index"] = global_index
                global_index += 1
            segments.extend(chunk_segs)
        logger.info("Transcription complete — %d segments across %d chunks for video %s", len(segments), len(chunk_paths), video_id)
    else:
        logger.info("Transcribing video %s (single audio file)", video_id)
        segments = run_asr(video_id, audio_path)
        logger.info("Transcription complete — %d segments for video %s", len(segments), video_id)

    if not segments:
        raise ValueError(f"ASR returned empty transcript for video {video_id}")

    for seg in segments:
        session.add(TranscriptSegment(
            video_id=video_id,
            job_id=job_id,
            segment_index=seg["segment_index"],
            start_time=seg["start_time"],
            end_time=seg["end_time"],
            text=seg["text"],
            words=seg["words"],
        ))

    transition(job, JobStatus.transcribed)
    video.status = "transcribed"
    session.commit()
    logger.info("Transcribed video %s — %d segments", video_id, len(segments))

    shots = session.execute(
        select(Shot).where(Shot.video_id == video_id).order_by(Shot.shot_index)
    ).scalars().all()
    shots_data = [{"start_time": s.start_time, "end_time": s.end_time} for s in shots]

    logger.info("Running segmentation for video %s", video_id)
    semantic_segs = run_segmentation(segments, shots_data)
    if not semantic_segs:
        logger.warning("Segmentation produced no segments for video %s — using full transcript", video_id)
        semantic_segs = [{
            "segment_index": 0,
            "start_time": segments[0]["start_time"],
            "end_time": segments[-1]["end_time"],
            "trigger_type": "full",
            "transcript_preview": segments[0].get("text", "")[:200],
        }]

    for seg in semantic_segs:
        session.add(SemanticSegment(
            video_id=video_id,
            segment_index=seg["segment_index"],
            start_time=seg["start_time"],
            end_time=seg["end_time"],
            trigger_type=seg["trigger_type"],
            transcript_preview=seg["transcript_preview"],
        ))
    session.commit()
    logger.info("Segmentation done — %d segments for video %s", len(semantic_segs), video_id)

    logger.info("Generating clip candidates for video %s", video_id)
    candidates = run_candidate_generation(segments, semantic_segs)
    if not candidates:
        raise ValueError(f"Candidate generation produced no candidates for video {video_id}")

    for c in candidates:
        session.add(ClipCandidate(
            video_id=video_id,
            candidate_index=c["candidate_index"],
            start_time=c["start_time"],
            end_time=c["end_time"],
            duration=c["duration"],
            candidate_type=c["candidate_type"],
            trigger_marker=c["trigger_marker"],
            transcript_preview=c["transcript_preview"],
        ))
    session.commit()
    logger.info("Generated %d clip candidates for video %s", len(candidates), video_id)

    logger.info("Computing features for video %s", video_id)
    db_candidates = session.execute(
        select(ClipCandidate).where(ClipCandidate.video_id == video_id)
    ).scalars().all()

    keyframes_dir = Path(settings.storage_root) / "videos" / str(video_id) / "keyframes"

    # audio_features needs a single WAV covering the full video.
    # For chunked videos, use the first chunk as a proxy (loudness/pace are
    # computed per-candidate using transcript timing, so this is acceptable).
    audio_features_path = audio_path if audio_path and audio_path.exists() else chunk_paths[0]

    for db_candidate in db_candidates:
        candidate_dict = {
            "start_time": db_candidate.start_time,
            "end_time": db_candidate.end_time,
            "duration": db_candidate.duration,
        }
        for key, value in compute_text_features(candidate_dict, segments).items():
            session.add(ClipFeature(candidate_id=db_candidate.id, feature_type="text", feature_key=key, feature_value=value))
        for key, value in compute_audio_features(candidate_dict, segments, audio_features_path).items():
            session.add(ClipFeature(candidate_id=db_candidate.id, feature_type="audio", feature_key=key, feature_value=value))
        for key, value in compute_video_features(candidate_dict, shots_data, keyframes_dir).items():
            session.add(ClipFeature(candidate_id=db_candidate.id, feature_type="video", feature_key=key, feature_value=value))
    session.commit()
    logger.info("Features computed for %d candidates of video %s", len(db_candidates), video_id)

    logger.info("Computing scores + ranking for video %s", video_id)
    db_candidates = session.execute(
        select(ClipCandidate).where(ClipCandidate.video_id == video_id)
    ).scalars().all()

    ranking_input = []
    for db_candidate in db_candidates:
        flat_features = {f.feature_key: f.feature_value for f in db_candidate.features}
        if not flat_features:
            logger.warning("No features for candidate %s — skipping scoring", db_candidate.id)
            continue
        scores = compute_specialist_scores(flat_features)
        ranking_input.append({
            "candidate_id": db_candidate.id,
            "scores": scores,
            "features": flat_features,
        })

    if not ranking_input:
        raise ValueError(f"No scoreable candidates for video {video_id}")

    ranked = rank_candidates(ranking_input)
    for entry in ranked:
        s = entry["scores"]
        session.add(ClipScore(
            candidate_id=entry["candidate_id"],
            hook_score=s["hook_score"],
            retention_score=s["retention_score"],
            share_score=s["share_score"],
            packaging_score=s["packaging_score"],
            risk_score=s["risk_score"],
            viral_score=entry["viral_score"],
            rank=entry["rank"],
            reasons=entry["reasons"],
        ))
    session.commit()
    logger.info(
        "Scoring done — %d ranked candidates, top viral_score=%.3f for video %s",
        len(ranked), ranked[0]["viral_score"], video_id,
    )

    # Cleanup: remove raw upload file to save space
    raw_path = video.original_path
    if raw_path and Path(raw_path).exists() and "raw." in Path(raw_path).name:
        try:
            Path(raw_path).unlink()
            logger.info("Deleted raw upload file %s", raw_path)
        except OSError as e:
            logger.warning("Could not delete raw file %s: %s", raw_path, e)


def _handle_failure(engine, payload: dict, exc: Exception) -> None:
    job_id_str = payload.get("job_id")
    if not job_id_str:
        return
    with Session(engine) as s:
        job = s.get(Job, uuid.UUID(job_id_str))
        if job is None:
            return
        job.retry_count = (job.retry_count or 0) + 1
        if job.retry_count < MAX_RETRIES:
            logger.warning(
                "ASR/processing failed (attempt %d/%d) for job %s — requeueing: %s",
                job.retry_count, MAX_RETRIES, job_id_str, exc,
            )
            job.status = JobStatus.ready_for_asr
            job.error_message = f"[attempt {job.retry_count}] {exc}"
            s.commit()
            r_retry = redis.from_url(settings.redis_url, decode_responses=True)
            r_retry.rpush(QUEUE_IN, json.dumps(payload))
        else:
            logger.error(
                "Processing permanently failed after %d attempts for job %s: %s",
                job.retry_count, job_id_str, exc,
            )
            job.status = JobStatus.failed
            job.error_message = str(exc)
            s.commit()


def main() -> None:
    logger.info("GPU worker starting — listening on %s", QUEUE_IN)
    r = redis.from_url(settings.redis_url, decode_responses=True)
    engine = create_engine(settings.database_url)

    while True:
        try:
            _, data = r.blpop(QUEUE_IN)
            payload = json.loads(data)
            with Session(engine) as session:
                try:
                    process(payload, session)
                except Exception as exc:
                    session.rollback()
                    logger.exception("Processing failed for job %s: %s", payload.get("job_id"), exc)
                    _handle_failure(engine, payload, exc)
        except Exception as exc:
            logger.exception("Unexpected worker error: %s", exc)


if __name__ == "__main__":
    main()
