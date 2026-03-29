"""CPU Worker — processes ingestion jobs from the Redis queue."""
import json
import logging
import uuid
from pathlib import Path

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.models import Job, JobStatus, Video
from services.ingestion import run_ingestion
from services.jobs import transition

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

QUEUE_IN = "queue:ingestion"
QUEUE_ASR = "queue:asr"


def process(payload: dict, session: Session, r: redis.Redis) -> None:
    job_id = uuid.UUID(payload["job_id"])
    video_id = uuid.UUID(payload["video_id"])

    job = session.get(Job, job_id)
    video = session.get(Video, video_id)

    if job is None or video is None:
        logger.error("Job %s or Video %s not found — skipping", job_id, video_id)
        return

    transition(job, JobStatus.ingesting)
    session.commit()
    logger.info("Ingesting video %s", video_id)

    result = run_ingestion(video_id, Path(video.original_path))

    video.duration_seconds = result["duration"]
    video.resolution = result["resolution"]
    video.fps = result["fps"]
    video.status = "ready_for_asr"
    transition(job, JobStatus.ready_for_asr)
    session.commit()

    r.lpush(QUEUE_ASR, json.dumps({"video_id": str(video_id), "job_id": str(job_id)}))
    logger.info("Video %s ingested — queued for ASR", video_id)


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
                    logger.exception("Ingestion failed: %s", exc)
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
