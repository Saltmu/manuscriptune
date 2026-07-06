import argparse
import sys

from src.services import findings_service
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply integrated findings to formatted novel draft."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory containing 01_formatted.txt and 00_integrated_findings.yaml",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt user for each finding in the terminal.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically apply all findings marked as accepted: 'y'.",
    )
    parser.add_argument(
        "--accept-ids",
        help="Comma-separated list of finding IDs to accept and apply (e.g. INT-001,INT-003).",
    )
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="LLM model for generating replacements.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM replacement, use local extraction rules instead.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    try:
        result = findings_service.apply_findings_in_dir(
            args.dir,
            interactive=args.interactive,
            auto=args.auto,
            accept_ids=args.accept_ids,
            model=args.model,
            no_llm=args.no_llm,
        )
    except findings_service.ApplyFindingsValidationError as e:
        logger.error(str(e))
        sys.exit(1)

    if (
        result.applied_count == 0
        and result.skipped_count == 0
        and result.failed_count == 0
    ):
        # 指摘が1件も無かったケース(既存の互換動作: 明示的にexit 0)
        sys.exit(0)


if __name__ == "__main__":
    main()
