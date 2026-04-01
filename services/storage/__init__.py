import uuid
from pathlib import Path

from apps.api.config import settings


def video_dir(video_id: uuid.UUID) -> Path:
    return Path(settings.storage_root) / "videos" / str(video_id)


def upload_path(video_id: uuid.UUID, filename: str) -> Path:
    """Return the destination path for a raw upload without creating the file."""
    ext = Path(filename).suffix.lower() or ".mp4"
    dest_dir = video_dir(video_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / f"raw{ext}"
