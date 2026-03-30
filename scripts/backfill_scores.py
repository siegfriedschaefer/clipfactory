"""Backfill features + scores for all candidates that have no clip_features yet.

Usage:
    python scripts/backfill_scores.py [video_id]

If video_id is omitted, processes all videos.
"""
import sys
import uuid
import logging
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.models import ClipCandidate, ClipFeature, ClipScore, Shot, TranscriptSegment

from services.audio_features import compute_audio_features
from services.features import compute_text_features
from services.video_features import compute_video_features
from services.scoring import compute_specialist_scores, rank_candidates

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def backfill_video(video_id: uuid.UUID, session: Session) -> None:
    candidates = session.execute(
        select(ClipCandidate).where(ClipCandidate.video_id == video_id)
    ).scalars().all()

    if not candidates:
        log.info("No candidates for %s — skipping", video_id)
        return

    # Skip if already has features
    already = session.execute(
        select(ClipFeature).where(
            ClipFeature.candidate_id == candidates[0].id
        ).limit(1)
    ).scalar_one_or_none()
    if already:
        log.info("Video %s already has features — skipping", video_id)
        return

    segments = session.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.segment_index)
    ).scalars().all()
    segments_data = [
        {"start_time": s.start_time, "end_time": s.end_time, "text": s.text}
        for s in segments
    ]

    shots = session.execute(
        select(Shot).where(Shot.video_id == video_id).order_by(Shot.shot_index)
    ).scalars().all()
    shots_data = [{"start_time": s.start_time, "end_time": s.end_time} for s in shots]

    audio_path = Path(settings.storage_root) / "videos" / str(video_id) / "audio.wav"
    keyframes_dir = Path(settings.storage_root) / "videos" / str(video_id) / "keyframes"

    log.info("Computing features for %d candidates of video %s", len(candidates), video_id)
    for c in candidates:
        cd = {"start_time": c.start_time, "end_time": c.end_time, "duration": c.duration}
        for key, value in compute_text_features(cd, segments_data).items():
            session.add(ClipFeature(candidate_id=c.id, feature_type="text", feature_key=key, feature_value=value))
        for key, value in compute_audio_features(cd, segments_data, audio_path).items():
            session.add(ClipFeature(candidate_id=c.id, feature_type="audio", feature_key=key, feature_value=value))
        for key, value in compute_video_features(cd, shots_data, keyframes_dir).items():
            session.add(ClipFeature(candidate_id=c.id, feature_type="video", feature_key=key, feature_value=value))
    session.commit()

    # Reload with features
    candidates = session.execute(
        select(ClipCandidate).where(ClipCandidate.video_id == video_id)
    ).scalars().all()

    ranking_input = [
        {
            "candidate_id": c.id,
            "scores": compute_specialist_scores({f.feature_key: f.feature_value for f in c.features}),
            "features": {f.feature_key: f.feature_value for f in c.features},
        }
        for c in candidates
    ]
    ranked = rank_candidates(ranking_input)

    for entry in ranked:
        s = entry["scores"]
        session.add(ClipScore(
            candidate_id=entry["candidate_id"],
            hook_score=s["hook_score"], retention_score=s["retention_score"],
            share_score=s["share_score"], packaging_score=s["packaging_score"],
            risk_score=s["risk_score"], viral_score=entry["viral_score"],
            rank=entry["rank"], reasons=entry["reasons"],
        ))
    session.commit()
    log.info("Done — top viral_score=%.3f", ranked[0]["viral_score"] if ranked else 0.0)


def main() -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        if len(sys.argv) > 1:
            backfill_video(uuid.UUID(sys.argv[1]), session)
        else:
            from apps.api.models import Video
            videos = session.execute(select(Video)).scalars().all()
            for v in videos:
                backfill_video(v.id, session)


if __name__ == "__main__":
    main()
