from apps.api.models import Job, JobStatus

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.uploaded: {JobStatus.ingesting},
    JobStatus.ingesting: {JobStatus.ready_for_asr, JobStatus.failed},
    JobStatus.ready_for_asr: {JobStatus.transcribing},
    JobStatus.transcribing: {JobStatus.transcribed, JobStatus.failed},
    JobStatus.transcribed: set(),
    JobStatus.failed: set(),
}


def transition(job: Job, new_status: JobStatus) -> None:
    """Apply a status transition. Raises ValueError for invalid transitions."""
    allowed = ALLOWED_TRANSITIONS.get(job.status, set()) | {JobStatus.failed}
    if new_status not in allowed:
        raise ValueError(
            f"Invalid job transition: {job.status.value!r} → {new_status.value!r}"
        )
    job.status = new_status
