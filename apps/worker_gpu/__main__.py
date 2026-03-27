"""GPU Worker entry point. Processes ASR jobs from the Redis queue."""
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("GPU worker starting — waiting for ASR jobs (WhisperX, Day 5-6)")
    # WhisperX integration implemented Day 5-6


if __name__ == "__main__":
    main()
