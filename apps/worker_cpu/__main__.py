"""CPU Worker — processes ingestion jobs from the Redis queue."""
import json
import logging
import uuid
from pathlib import Path

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.models import Job, JobStatus, Shot, Video
from services.ingestion import run_ingestion
from services.jobs import transition
from services.logging_config import setup
from services.shot_detection import run_shot_detection

setup()
logger = logging.getLogger(__name__)

QUEUE_IN = "queue:ingestion"
QUEUE_ASR = "queue:asr"
MAX_RETRIES = 3


def process(payload: dict, session: Session, r: redis.Redis) -> None:
    job_id = uuid.UUID(payload["job_id"])
    video_id = uuid.UUID(payload["video_id"])

    job = session.get(Job, job_id)
    video = session.get(Video, video_id)

    if job is None or video is None:
        logger.error("Job or video not found", extra={"job_id": str(job_id), "video_id": str(video_id)})
        return

    # Guard: skip if already past ingestion (duplicate message)
    if job.status not in (JobStatus.uploaded, JobStatus.failed):
        logger.warning("Job %s already in status %s — skipping", job_id, job.status)
        return

    # Validate source file exists
    raw_path = Path(video.original_path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Source file not found: {raw_path}")

    transition(job, JobStatus.ingesting)
    session.commit()
    logger.info("Ingesting video %s", video_id)

    result = run_ingestion(video_id, raw_path)

    if not result["duration"] or result["duration"] <= 0:
        raise ValueError(f"Invalid video duration: {result['duration']}")

    video.duration_seconds = result["duration"]
    video.resolution = result["resolution"]
    video.fps = result["fps"]
    session.commit()

    if result["chunk_paths"]:
        logger.info(
            "Video %s is %.0fs — split into %d audio chunks",
            video_id, result["duration"], len(result["chunk_paths"]),
        )
    else:
        logger.info("Video %s is %.0fs — single audio file", video_id, result["duration"])

    logger.info("Running shot detection for video %s", video_id)
    shots = run_shot_detection(video_id, result["normalized_path"])
    for shot in shots:
        session.add(Shot(video_id=video_id, **shot))
    session.commit()
    logger.info("Shot detection done — %d shots for video %s", len(shots), video_id)

    video.status = "ready_for_asr"
    transition(job, JobStatus.ready_for_asr)
    session.commit()

    r.lpush(QUEUE_ASR, json.dumps({"video_id": str(video_id), "job_id": str(job_id)}))
    logger.info("Video %s ingested successfully — queued for ASR", video_id)


def _handle_failure(engine, payload: dict, exc: Exception, r: redis.Redis) -> None:
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
                "Ingestion failed (attempt %d/%d) for job %s — requeueing: %s",
                job.retry_count, MAX_RETRIES, job_id_str, exc,
            )
            job.status = JobStatus.uploaded
            job.error_message = f"[attempt {job.retry_count}] {exc}"
            s.commit()
            r.rpush(QUEUE_IN, json.dumps(payload))
        else:
            logger.error(
                "Ingestion permanently failed after %d attempts for job %s: %s",
                job.retry_count, job_id_str, exc,
            )
            job.status = JobStatus.failed
            job.error_message = str(exc)
            s.commit()


def main() -> None:
    logger.info("CPU worker starting — listening on %s", QUEUE_IN)
    r = redis.from_url(settings.redis_url, decode_responses=True)
    engine = create_engine(settings.database_url)

    while True:
        try:
            _, data = r.blpop(QUEUE_IN)
            payload = json.loads(data)
            with Session(engine) as session:
                try:
                    process(payload, session, r)
                except Exception as exc:
                    session.rollback()
                    logger.exception("Ingestion failed for job %s: %s", payload.get("job_id"), exc)
                    _handle_failure(engine, payload, exc, r)
        except Exception as exc:
            logger.exception("Unexpected worker error: %s", exc)


if __name__ == "__main__":
    main()
