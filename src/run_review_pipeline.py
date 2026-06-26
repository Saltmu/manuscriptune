import argparse
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.utils import project_paths
from src.utils.ai_client import AgyClientError
from src.utils.ai_task import ReviewSkillInput, ReviewSkillTask
from src.utils.file_io import read_file


def archive_previous_review(output_dir, basename):
    """
    Archives the current [basename]_formatted.txt, [basename]_findings.yaml,
    and [basename]_report.md into a history directory.
    """
    history_dir = os.path.join(output_dir, "history")
    findings_file = project_paths.get_findings_yaml_path(output_dir, basename)

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
        f"\n[Archive] Existing review findings found. Archiving to history/{v_prefix}_{basename}_..."
    )

    # Files to archive
    files_to_archive = {
        f"{basename}_formatted.txt": f"{v_prefix}_{basename}_formatted.txt",
        f"{basename}_findings.yaml": f"{v_prefix}_{basename}_findings.yaml",
        f"{basename}_report.md": f"{v_prefix}_{basename}_report.md",
        "01_filtered_context.txt": f"{v_prefix}_filtered_context.txt",
    }

    for src_name, dest_name in files_to_archive.items():
        src_path = os.path.join(output_dir, src_name)
        dest_path = os.path.join(history_dir, dest_name)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dest_path)
            print(f"  Archived: {src_name} -> history/{dest_name}")

    # Clean up current findings and report so they are regenerated
    for src_name in [f"{basename}_findings.yaml", f"{basename}_report.md"]:
        src_path = os.path.join(output_dir, src_name)
        if os.path.exists(src_path):
            os.remove(src_path)


def run_formatter(input_file, output_file):
    """
    Runs the novel mechanical formatter on the input file.
    """
    formatter_script = os.path.join(
        "skills", "novel-formatter", "scripts", "novel_formatter_helper.py"
    )
    if not os.path.exists(formatter_script):
        print(
            f"Warning: Formatter script '{formatter_script}' not found. Performing fallback copy."
        )
        content = read_file(input_file)
        content = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", content)
        content = re.sub(r"\(\d+(?:,\s*\d+)*\)", "", content)
        content = re.sub(r"【\d+(?:,\s*\d+)*】", "", content)
        content = re.sub(r"([。、！？])[\t 　]+", r"\1", content)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        return

    cmd = ["poetry", "run", "python", formatter_script, input_file, "-o", output_file]
    print(f"Running mechanical formatter: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def run_filter_context(formatted_file, output_file):
    """
    Runs the filter_context script to extract relevant settings.
    """
    filter_script = os.path.join("src", "filter_context.py")
    if not os.path.exists(filter_script):
        print("Warning: filter_context.py not found. Skipping context filtering.")
        return False

    cmd = ["poetry", "run", "python", filter_script, formatted_file, output_file]
    print(f"Running context filter: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return True
    else:
        print(
            f"Warning: Context filter failed with error:\n{res.stderr}", file=sys.stderr
        )
        return False


def run_single_review_skill(skill_name, target_text, output_file, model, output_dir):
    """
    Executes a single review skill via ReviewSkillTask.
    """
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


def _resolve_output_dir(target_path: Path, args_dir: str | None) -> tuple[str, str]:
    """
    Resolves basename and output directory.
    """
    if "novel_check_results" in target_path.parts:
        idx = target_path.parts.index("novel_check_results")
        if idx + 1 < len(target_path.parts):
            basename = target_path.parts[idx + 1]
            output_dir = os.path.join("novel_check_results", basename)
            return basename, output_dir

    basename = target_path.stem
    output_dir = args_dir if args_dir else os.path.join("novel_check_results", basename)
    return basename, output_dir


def _run_step_format(
    target_path: Path, formatted_draft: str, output_dir: str, basename: str
) -> None:
    """
    Executes Step 1: mechanical formatter and archiving if needed.
    """
    findings_file = os.path.join(output_dir, f"{basename}_findings.yaml")
    is_rereview = os.path.exists(findings_file)

    if is_rereview:
        archive_previous_review(output_dir, basename)
        print(f"[INFO] Re-reviewing existing formatted draft: {formatted_draft}")
    elif not os.path.exists(formatted_draft):
        try:
            run_formatter(str(target_path), formatted_draft)
            print(f"[OK] Format completed: {formatted_draft}\n")
        except Exception as e:
            print(f"[ERROR] Formatting failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(
            f"[INFO] Formatted draft already exists. Skipping formatting: {formatted_draft}"
        )


def _run_step_parallel_reviews(
    target_text: str, output_dir: str, model: str, workers: int
) -> None:
    """
    Executes Step 3: parallel execution of review skills.
    """
    review_skills = {
        "logic-consistency-reviewer": "02_logic_consistency.yaml",
        "style-expression-reviewer": "03_style_expression.yaml",
    }
    results = []

    print(f"Spawning {len(review_skills)} review skills in parallel...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for skill, yaml_name in review_skills.items():
            output_yaml = os.path.join(output_dir, yaml_name)
            futures[
                executor.submit(
                    run_single_review_skill,
                    skill,
                    target_text,
                    output_yaml,
                    model,
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


def _run_step_integration(output_dir: str, basename: str, model: str) -> None:
    """
    Executes Step 4: integrates all findings into a final report.
    """
    print("\nIntegrating review results...")
    try:
        import integrate_findings

        print(
            f"Calling: integrate_findings.integrate_findings_in_dir(output_dir='{output_dir}', model='{model}')"
        )
        success = integrate_findings.integrate_findings_in_dir(output_dir, model)
        if success:
            print("[OK] Reports integrated successfully.")
            print(
                f"Consolidated Report: {os.path.join(output_dir, f'{basename}_report.md')}"
            )
            print(
                f"Consolidated YAML  : {os.path.join(output_dir, f'{basename}_findings.yaml')}"
            )
        else:
            print(
                "[ERROR] Failed to integrate findings.",
                file=sys.stderr,
            )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error while calling integrate_findings: {e}",
            file=sys.stderr,
        )


def _run_step_server(
    formatted_draft: str, output_dir: str, basename: str, no_server: bool
) -> None:
    """
    Executes Step 5: launches the interactive review editor server.
    """
    if not no_server:
        print("\nStarting Interactive Review Editor UI...")
        server_script = os.path.join("src", "review_server.py")
        if os.path.exists(server_script):
            cmd = [
                "poetry",
                "run",
                "python",
                server_script,
                formatted_draft,
                os.path.join(output_dir, f"{basename}_findings.yaml"),
            ]
            print(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd)
        else:
            print(
                "[WARNING] review_server.py not found. Interactive UI skipped.",
                file=sys.stderr,
            )


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
        help="Output directory path (defaults to novel_check_results/[basename])",
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

    target_path = Path(args.target_file)

    # Smart path resolution
    basename, output_dir = _resolve_output_dir(target_path, args.dir)

    os.makedirs(output_dir, exist_ok=True)

    print("=== Review Pipeline Starting ===")
    print(f"Target: {target_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Model: {args.model}\n")

    # Step 1: Run Formatter (or Skip if it's a re-review)
    formatted_draft = project_paths.get_formatted_draft_path(output_dir, basename)
    _run_step_format(target_path, formatted_draft, output_dir, basename)

    # Step 2: Run Context Filter
    filtered_context = os.path.join(output_dir, "01_filtered_context.txt")
    run_filter_context(formatted_draft, filtered_context)

    # Read formatted draft text
    target_text = read_file(formatted_draft)

    # Step 3: Run parallel reviews
    _run_step_parallel_reviews(target_text, output_dir, args.model, args.workers)

    # Step 4: Run integration report
    _run_step_integration(output_dir, basename, args.model)

    # Step 5: Start Review Editor Server
    _run_step_server(formatted_draft, output_dir, basename, args.no_server)

    print("\n=== Review Pipeline Finished ===")


if __name__ == "__main__":
    main()
