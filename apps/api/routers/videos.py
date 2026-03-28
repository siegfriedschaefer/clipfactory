import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models import Video
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


@router.post("", response_model=VideoResponse, status_code=201)
async def upload_video(
    file: UploadFile,
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
    await session.flush()

    return VideoResponse.model_validate(video)
