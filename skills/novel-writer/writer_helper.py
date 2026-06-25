import argparse
import os

from src.utils.plot_parser import get_chapter_episodes, list_chapters, parse_plot
from src.utils.project_config import resolve_novel_file_by_pattern

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse novel plot files.")
    default_plot = resolve_novel_file_by_pattern(
        "plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt"
    )
    parser.add_argument("--file", default=default_plot, help="Path to the plot file.")
    parser.add_argument(
        "--list", action="store_true", help="List all chapters and episodes."
    )
    parser.add_argument(
        "--get-chapter",
        type=str,
        help="Get episodes for a specific chapter (e.g., '第1章').",
    )

    args = parser.parse_args()

    # Adjust path if relative
    plot_file = args.file
    if not os.path.isabs(plot_file):
        # Assuming project root is current working directory
        pass

    if os.path.exists(plot_file):
        plot_data = parse_plot(plot_file)

        if args.list:
            list_chapters(plot_data)
        elif args.get_chapter:
            episodes = get_chapter_episodes(plot_data, args.get_chapter)
            if episodes:
                import json

                print(json.dumps(episodes, ensure_ascii=False, indent=2))
            else:
                print(f"Chapter {args.get_chapter} not found.")
    else:
        print(f"File not found: {plot_file}")
