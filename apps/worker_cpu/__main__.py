"""CPU Worker entry point. Processes ingestion jobs from the Redis queue."""
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("CPU worker starting — waiting for jobs (ingestion, ffmpeg)")
    # Job queue polling implemented Day 3-4


if __name__ == "__main__":
    main()
