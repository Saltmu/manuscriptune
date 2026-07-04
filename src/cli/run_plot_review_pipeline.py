import argparse
import sys

from src.services.pipeline_service import PlotReviewPipeline
from src.utils.ai_exceptions import PipelineError
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Run the parallel plot review pipeline."
    )
    parser.add_argument("target_file", help="Path to the plot txt file to review.")
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="AI Model to use for review skills.",
    )
    parser.add_argument(
        "--dir",
        help="Output directory path (defaults to reviews/[basename])",
    )
    parser.add_argument(
        "--workers", type=int, default=2, help="Number of parallel worker threads."
    )
    args = parser.parse_args()

    try:
        pipeline = PlotReviewPipeline(
            target_file=args.target_file,
            model=args.model,
            output_dir_override=args.dir,
            workers=args.workers,
        )
        pipeline.execute()
    except PipelineError as e:
        logger.error(f"Plot review pipeline failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unhandled critical error in plot pipeline: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
