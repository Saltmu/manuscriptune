import argparse
import sys

from src.services import writer_service
from src.utils import project_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use Antigravity CLI (agy) to write a novel episode."
    )
    parser.add_argument(
        "--episode", required=True, help="Episode title (e.g., '第1話')"
    )
    default_plot = project_config.resolve_novel_file_by_pattern(
        "plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt"
    )
    parser.add_argument(
        "--plot-file", default=default_plot, help="Path to the plot file."
    )
    parser.add_argument(
        "--model",
        default=writer_service.DEFAULT_MODEL,
        help="Model name (Gemini 3.5 Flash (High), etc.)",
    )
    parser.add_argument("--title", help="Novel title.")
    parser.add_argument("--policy-global", help="Path to global policy file.")
    parser.add_argument("--policy-chapter", help="Path to chapter policy file.")
    parser.add_argument("--character", help="Path to character overview file.")
    parser.add_argument(
        "--step-by-step", action="store_true", help="Write the episode scene by scene."
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Perform self-check/rewrite on output.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Print the generated prompt and exit.",
    )
    parser.add_argument(
        "--include-neighbor-plots",
        action="store_true",
        help="Include plot content of neighboring (previous and next) episodes in the prompt.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    service = writer_service.WriterService()

    def on_line(line: str) -> None:
        sys.stdout.write(line)
        sys.stdout.flush()

    kwargs = {
        "episode": args.episode,
        "plot_file": args.plot_file,
        "model": args.model,
        "title": args.title,
        "policy_global": args.policy_global,
        "policy_chapter": args.policy_chapter,
        "character": args.character,
        "include_neighbor_plots": args.include_neighbor_plots,
    }

    try:
        if args.prompt_only:
            print(service.generate_prompt(**kwargs))
            sys.exit(0)

        service.execute(
            **kwargs,
            step_by_step=args.step_by_step,
            self_check=args.self_check,
            on_line=on_line,
        )
    except writer_service.WriterServiceError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: 'agy' CLI not found. Please ensure it is installed and in your PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
