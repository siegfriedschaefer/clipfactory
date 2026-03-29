"""GPU Worker — processes ASR jobs from the Redis queue using Moonshine."""
import json
import logging
import uuid
from pathlib import Path

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.models import Job, JobStatus, TranscriptSegment, Video
from services.asr import run_asr
from services.jobs import transition

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

QUEUE_IN = "queue:asr"


def process(payload: dict, session: Session) -> None:
    job_id = uuid.UUID(payload["job_id"])
    video_id = uuid.UUID(payload["video_id"])

    job = session.get(Job, job_id)
    video = session.get(Video, video_id)

    if job is None or video is None:
        logger.error("Job %s or Video %s not found — skipping", job_id, video_id)
        return

    transition(job, JobStatus.transcribing)
    video.status = "transcribing"
    session.commit()
    logger.info("Transcribing video %s", video_id)

    audio_path = Path(settings.storage_root) / "videos" / str(video_id) / "audio.wav"
    segments = run_asr(video_id, audio_path)

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
    logger.info("Video %s transcribed — %d segments", video_id, len(segments))


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
                    logger.exception("ASR failed: %s", exc)
                    job_id_str = payload.get("job_id")
                    if job_id_str:
                        with Session(engine) as err_session:
                            job = err_session.get(Job, uuid.UUID(job_id_str))
                            if job:
                                job.status = JobStatus.failed
                                job.error_message = str(exc)
                                err_session.commit()
        except Exception as exc:
            logger.exception("Unexpected worker error: %s", exc)


if __name__ == "__main__":
    main()
