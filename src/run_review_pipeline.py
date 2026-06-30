import argparse
import sys

from src.services.pipeline_service import TextReviewPipeline
from src.utils.ai_exceptions import PipelineError
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Run the entire parallel review pipeline for a novel draft."
    )
    parser.add_argument("target_file", help="Path to the novel txt file to review.")
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
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Skip launching the web server editor at the end.",
    )
    args = parser.parse_args()

    try:
        pipeline = TextReviewPipeline(
            target_file=args.target_file,
            model=args.model,
            output_dir_override=args.dir,
            workers=args.workers,
        )
        pipeline.execute(no_server=args.no_server)
    except PipelineError as e:
        logger.error(f"Pipeline execution failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unhandled critical error in pipeline: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
