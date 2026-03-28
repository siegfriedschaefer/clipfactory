import uuid
from pathlib import Path

from apps.api.config import settings


def video_dir(video_id: uuid.UUID) -> Path:
    return Path(settings.storage_root) / "videos" / str(video_id)


def save_upload(video_id: uuid.UUID, filename: str, data: bytes) -> Path:
    """Write uploaded file to /storage/videos/{video_id}/raw.{ext} and return the path."""
    ext = Path(filename).suffix.lower() or ".mp4"
    dest_dir = video_dir(video_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"raw{ext}"
    dest.write_bytes(data)
    return dest
