import json
import uuid
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.database import get_session
from apps.api.models import Job, JobStatus, TranscriptSegment, Video
from services.storage import save_upload

router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB


class VideoResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobStatusResponse(BaseModel):
    video_id: uuid.UUID
    job_id: uuid.UUID
    status: str
    error_message: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SegmentResponse(BaseModel):
    segment_index: int
    start_time: float
    end_time: float
    text: str
    words: list | None

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    video_id: uuid.UUID
    segments: list[SegmentResponse]


@router.post("", response_model=VideoResponse, status_code=201)
async def upload_video(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> VideoResponse:
    """Upload a video file. Creates a DB record and stores the raw file."""
    from pathlib import Path

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 4 GB limit.")

    video_id = uuid.uuid4()
    saved_path = save_upload(video_id, file.filename, data)

    video = Video(
        id=video_id,
        filename=file.filename,
        original_path=str(saved_path),
        status="uploaded",
    )
    session.add(video)

    job = Job(video_id=video_id, status=JobStatus.uploaded)
    session.add(job)
    await session.flush()

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await r.lpush(
            "queue:ingestion",
            json.dumps({"video_id": str(video_id), "job_id": str(job.id)}),
        )
    finally:
        await r.aclose()

    return VideoResponse.model_validate(video)


@router.get("/{video_id}/status", response_model=JobStatusResponse)
async def get_status(
    video_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JobStatusResponse:
    """Return the current job status for a video."""
    result = await session.execute(
        select(Job).where(Job.video_id == video_id).order_by(Job.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="No job found for this video.")
    return JobStatusResponse(
        video_id=video_id,
        job_id=job.id,
        status=job.status.value,
        error_message=job.error_message,
        updated_at=job.updated_at,
    )


@router.get("/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    video_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TranscriptResponse:
    """Return all transcript segments for a video."""
    result = await session.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.segment_index)
    )
    segments = result.scalars().all()
    if not segments:
        raise HTTPException(status_code=404, detail="No transcript found for this video.")
    return TranscriptResponse(
        video_id=video_id,
        segments=[SegmentResponse.model_validate(s) for s in segments],
    )
