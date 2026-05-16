import asyncio

from src.processing.worker.consumer import run_worker


def main() -> None:
    """Run the processing worker."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
