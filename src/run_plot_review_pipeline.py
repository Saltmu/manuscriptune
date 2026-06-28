import argparse
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src import integrate_plot_findings
from src.utils.ai_client import AgyClientError
from src.utils.ai_task import ReviewSkillInput, ReviewSkillTask
from src.utils.file_io import read_file


def archive_previous_plot_review(output_dir, basename):
    """Archives the current [basename]_plot_findings.yaml and [basename]_plot_report.md

    into a history directory.
    """
    history_dir = os.path.join(output_dir, "history")
    findings_file = os.path.join(output_dir, f"{basename}_plot_findings.yaml")

    if not os.path.exists(findings_file):
        return

    os.makedirs(history_dir, exist_ok=True)

    # Determine version number (v1, v2, v3...)
    existing_versions = []
    version_pattern = re.compile(rf"v(\d+)_(?:{re.escape(basename)})_")
    if os.path.exists(history_dir):
        for f in os.listdir(history_dir):
            match = version_pattern.match(f)
            if match:
                existing_versions.append(int(match.group(1)))

    next_version = max(existing_versions) + 1 if existing_versions else 1
    v_prefix = f"v{next_version}"

    print(
        f"\n[Archive] Existing plot review findings found. Archiving to history/{v_prefix}_{basename}_..."
    )

    # Files to archive
    files_to_archive = {
        f"{basename}_plot_findings.yaml": f"{v_prefix}_{basename}_plot_findings.yaml",
        f"{basename}_plot_report.md": f"{v_prefix}_{basename}_plot_report.md",
    }

    for src_name, dest_name in files_to_archive.items():
        src_path = os.path.join(output_dir, src_name)
        dest_path = os.path.join(history_dir, dest_name)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dest_path)
            print(f"  Archived: {src_name} -> history/{dest_name}")

    # Clean up current findings and report so they are regenerated
    for src_name in [f"{basename}_plot_findings.yaml", f"{basename}_plot_report.md"]:
        src_path = os.path.join(output_dir, src_name)
        if os.path.exists(src_path):
            os.remove(src_path)


def run_single_review_skill(skill_name, target_text, output_file, model, output_dir):
    """Executes a single review skill via ReviewSkillTask."""
    print(f"[{skill_name}] Preparing review prompt...")
    task = ReviewSkillTask(model=model)
    input_data = ReviewSkillInput(
        skill_name=skill_name, target_text=target_text, output_dir=output_dir
    )

    print(f"[{skill_name}] Running AgyClient ({model})...")
    try:
        yaml_content = task.execute(input_data)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(yaml_content + "\n")

        return skill_name, True, f"Saved to {output_file}"

    except AgyClientError as e:
        return skill_name, False, str(e)
    except Exception as e:
        return skill_name, False, f"Unexpected error: {str(e)}"


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
        help="Output directory path (defaults to novel_check_results/[basename])",
    )
    parser.add_argument(
        "--workers", type=int, default=2, help="Number of parallel worker threads."
    )
    args = parser.parse_args()

    target_path = Path(args.target_file)
    basename = target_path.stem
    output_dir = args.dir if args.dir else os.path.join("novel_check_results", basename)

    os.makedirs(output_dir, exist_ok=True)

    print("=== Plot Review Pipeline Starting ===")
    print(f"Target Plot: {target_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Model: {args.model}\n")

    # Step 1: Archive previous review if exists
    archive_previous_plot_review(output_dir, basename)

    # Read plot text
    target_text = read_file(str(target_path))
    if not target_text:
        print(
            f"[ERROR] Could not read target plot file: {target_path}", file=sys.stderr
        )
        sys.exit(1)

    # Step 2: Run parallel review skills
    review_skills = {
        "plot-reviewer-conflict": "02_plot_conflict.yaml",
        "plot-reviewer-structure": "03_plot_structure.yaml",
    }
    results = []

    print(f"Spawning {len(review_skills)} plot review skills in parallel...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for skill, yaml_name in review_skills.items():
            output_yaml = os.path.join(output_dir, yaml_name)
            futures[
                executor.submit(
                    run_single_review_skill,
                    skill,
                    target_text,
                    output_yaml,
                    args.model,
                    output_dir,
                )
            ] = skill

        for future in as_completed(futures):
            skill = futures[future]
            try:
                skill_name, success, msg = future.result()
                results.append((skill_name, success, msg))
                if success:
                    print(f"[OK] {skill_name}: {msg}")
                else:
                    print(f"[FAIL] {skill_name}: {msg}", file=sys.stderr)
            except Exception as exc:
                print(f"[FAIL] {skill} generated an exception: {exc}", file=sys.stderr)
                results.append((skill, False, str(exc)))

    # Step 3: Run integration report
    print("\nIntegrating plot review results...")
    success = integrate_plot_findings.integrate_plot_findings_in_dir(
        output_dir, str(target_path), args.model
    )
    if success:
        print("[OK] Plot reports integrated successfully.")
        print(
            f"Consolidated Report: {os.path.join(output_dir, f'{basename}_plot_report.md')}"
        )
        print(
            f"Consolidated YAML  : {os.path.join(output_dir, f'{basename}_plot_findings.yaml')}"
        )
    else:
        print("[ERROR] Failed to integrate plot findings.", file=sys.stderr)
        sys.exit(1)

    print("\n=== Plot Review Pipeline Finished ===")


if __name__ == "__main__":
    main()
