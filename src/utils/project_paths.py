import os

DEFAULT_RESULTS_DIR = "reviews"


def get_output_dir(basename: str, results_dir: str = DEFAULT_RESULTS_DIR) -> str:
    """Returns the output directory path for a given novel basename."""
    # Resolve relative to project root or use as-is
    return os.path.join(results_dir, basename)


def get_formatted_draft_path(output_dir: str, basename: str) -> str:
    """Returns the standard path for the formatted draft text."""
    return os.path.join(output_dir, f"{basename}_formatted.txt")


def resolve_formatted_draft_path(output_dir: str, basename: str) -> str:
    """Resolves the path to the formatted draft text.

    Uses {basename}_formatted.txt if it exists, falling back to 01_formatted.txt.
    """
    path = get_formatted_draft_path(output_dir, basename)
    if not os.path.exists(path):
        fallback = os.path.join(output_dir, "01_formatted.txt")
        if os.path.exists(fallback):
            return fallback
    return path


def get_findings_yaml_path(output_dir: str, basename: str) -> str:
    """Returns the standard path for the integrated findings YAML."""
    return os.path.join(output_dir, f"{basename}_findings.yaml")


def resolve_findings_yaml_path(output_dir: str, basename: str) -> str:
    """Resolves the path to the integrated findings YAML.

    Uses {basename}_findings.yaml if it exists, falling back to 00_integrated_findings.yaml.
    """
    path = get_findings_yaml_path(output_dir, basename)
    if not os.path.exists(path):
        fallback = os.path.join(output_dir, "00_integrated_findings.yaml")
        if os.path.exists(fallback):
            return fallback
    return path


def get_report_md_path(output_dir: str, basename: str) -> str:
    """Returns the expected path for the final Markdown report."""
    return os.path.join(output_dir, f"{basename}_report.md")
