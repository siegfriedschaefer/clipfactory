import asyncio
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.config import settings
from apps.api.database import get_session
from apps.api.models import (
    ClipCandidate, ClipFeedback, ClipScore, ClipVariant,
    Job, JobStatus, Shot, TranscriptSegment, Video,
)
from services.storage import save_upload, video_dir

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


class CandidateResponse(BaseModel):
    id: uuid.UUID
    candidate_index: int
    start_time: float
    end_time: float
    duration: float
    candidate_type: str
    trigger_marker: str | None
    transcript_preview: str | None
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    session: AsyncSession = Depends(get_session),
) -> list[VideoResponse]:
    """Return all videos ordered by upload time (newest first)."""
    result = await session.execute(select(Video).order_by(Video.created_at.desc()))
    videos = result.scalars().all()
    return [VideoResponse.model_validate(v) for v in videos]


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


@router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a video, all its DB records, and all storage artifacts."""
    result = await session.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    await session.delete(video)
    await session.flush()

    storage_path = video_dir(video_id)
    if storage_path.exists():
        shutil.rmtree(storage_path)


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


class RankedClipResponse(BaseModel):
    rank: int
    candidate_id: uuid.UUID
    start_time: float
    end_time: float
    duration: float
    candidate_type: str
    viral_score: float
    hook_score: float
    retention_score: float
    share_score: float
    packaging_score: float
    risk_score: float
    reasons: list[str]
    transcript_preview: str | None
    title_suggestions_v0: list[str]


@router.get("/{video_id}/ranked-clips", response_model=list[RankedClipResponse])
async def get_ranked_clips(
    video_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[RankedClipResponse]:
    """Return Top-10 ranked clip candidates for a video with scores and reasons."""
    result = await session.execute(
        select(ClipCandidate)
        .where(ClipCandidate.video_id == video_id)
        .options(selectinload(ClipCandidate.score))
        .order_by(ClipCandidate.candidate_index)
    )
    candidates = result.scalars().all()
    if not candidates:
        raise HTTPException(status_code=404, detail="No candidates found for this video.")

    scored = [c for c in candidates if c.score is not None]
    if not scored:
        raise HTTPException(status_code=404, detail="Ranking not yet computed for this video.")

    top10 = sorted(scored, key=lambda c: c.score.rank)[:10]

    return [
        RankedClipResponse(
            rank=c.score.rank,
            candidate_id=c.id,
            start_time=c.start_time,
            end_time=c.end_time,
            duration=c.duration,
            candidate_type=c.candidate_type,
            viral_score=c.score.viral_score,
            hook_score=c.score.hook_score,
            retention_score=c.score.retention_score,
            share_score=c.score.share_score,
            packaging_score=c.score.packaging_score,
            risk_score=c.score.risk_score,
            reasons=c.score.reasons or [],
            transcript_preview=c.transcript_preview,
            title_suggestions_v0=_title_suggestions(c.transcript_preview),
        )
        for c in top10
    ]


def _title_suggestions(preview: str | None) -> list[str]:
    """Generate simple title suggestions from the transcript preview."""
    if not preview:
        return []

    import re
    # Take the first sentence
    sentences = [s.strip() for s in re.split(r"[.!?]+", preview) if s.strip()]
    if not sentences:
        return []

    base = sentences[0]
    # Truncate to ~80 chars
    if len(base) > 80:
        base = base[:77] + "..."

    suggestions = [base]

    # Variant: prefix with a number if one exists in the preview
    numbers = re.findall(r"\b\d+(?:[.,]\d+)?(?:\s*%|x|X)?\b", preview)
    if numbers:
        suggestions.append(f"{numbers[0]}: {base}")

    return suggestions[:2]


@router.get("/{video_id}/candidates", response_model=list[CandidateResponse])
async def get_candidates(
    video_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CandidateResponse]:
    """Return all clip candidates for a video ordered by start time."""
    result = await session.execute(
        select(ClipCandidate)
        .where(ClipCandidate.video_id == video_id)
        .order_by(ClipCandidate.candidate_index)
    )
    candidates = result.scalars().all()
    if not candidates:
        raise HTTPException(status_code=404, detail="No candidates found for this video.")
    return [CandidateResponse.model_validate(c) for c in candidates]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportResponse(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    variant_type: str
    file_path: str
    resolution: str | None
    title_suggestions: list | None
    subtitle_path: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/{video_id}/candidates/{candidate_id}/export", response_model=ExportResponse, status_code=201)
async def export_candidate(
    video_id: uuid.UUID,
    candidate_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ExportResponse:
    """Render and export a 9:16 MP4 with burned-in subtitles for a clip candidate."""
    from services.packaging import export_clip

    result = await session.execute(
        select(ClipCandidate).where(
            ClipCandidate.id == candidate_id,
            ClipCandidate.video_id == video_id,
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Check not already exported
    existing = await session.execute(
        select(ClipVariant).where(
            ClipVariant.candidate_id == candidate_id,
            ClipVariant.variant_type == "export",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Export already exists for this candidate.")

    # Load transcript segments
    segs_result = await session.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.segment_index)
    )
    segments = [
        {"start_time": s.start_time, "end_time": s.end_time, "text": s.text}
        for s in segs_result.scalars().all()
    ]

    # Load shots
    shots_result = await session.execute(
        select(Shot).where(Shot.video_id == video_id).order_by(Shot.shot_index)
    )
    shots = [
        {"start_time": s.start_time, "end_time": s.end_time}
        for s in shots_result.scalars().all()
    ]

    # Load title suggestions from score
    score_result = await session.execute(
        select(ClipScore).where(ClipScore.candidate_id == candidate_id)
    )
    score = score_result.scalar_one_or_none()
    title_suggestions = _title_suggestions(candidate.transcript_preview)

    storage_root = Path(settings.storage_root)

    # Run ffmpeg in a thread so we don't block the event loop
    output = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: export_clip(
            video_id=video_id,
            candidate_id=candidate_id,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
            transcript_segments=segments,
            shots=shots,
            storage_root=storage_root,
        ),
    )

    variant = ClipVariant(
        candidate_id=candidate_id,
        variant_type="export",
        file_path=output["file_path"],
        resolution=output["resolution"],
        title_suggestions=title_suggestions,
        overlay_text=title_suggestions[0] if title_suggestions else None,
        subtitle_path=output.get("subtitle_path"),
    )
    session.add(variant)
    await session.commit()
    await session.refresh(variant)
    return ExportResponse.model_validate(variant)


@router.get("/{video_id}/exports", response_model=list[ExportResponse])
async def get_exports(
    video_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ExportResponse]:
    """Return all export artefacts for a video."""
    result = await session.execute(
        select(ClipVariant)
        .join(ClipCandidate, ClipVariant.candidate_id == ClipCandidate.id)
        .where(ClipCandidate.video_id == video_id)
        .order_by(ClipVariant.created_at.desc())
    )
    variants = result.scalars().all()
    return [ExportResponse.model_validate(v) for v in variants]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    action: str  # positive | negative | exported


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    action: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/{video_id}/candidates/{candidate_id}/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    video_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: FeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """Record user feedback for a clip candidate."""
    valid_actions = {"positive", "negative", "exported"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"action must be one of {valid_actions}")

    result = await session.execute(
        select(ClipCandidate).where(
            ClipCandidate.id == candidate_id,
            ClipCandidate.video_id == video_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    fb = ClipFeedback(candidate_id=candidate_id, video_id=video_id, action=body.action)
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return FeedbackResponse.model_validate(fb)
