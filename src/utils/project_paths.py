import os

# Project Directory Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

NOVELS_DIR = "novels"
DATA_DIR = "data"
SOURCES_DIR = "sources"
DATA_SOURCES_DIR = os.path.join(DATA_DIR, SOURCES_DIR)

DEFAULT_RESULTS_DIR = "reviews"
DEFAULT_LOGS_DIR = "logs"


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


def get_novels_dir() -> str:
    """Returns the absolute path to the novels directory."""
    return os.path.join(PROJECT_ROOT, NOVELS_DIR)


def get_sources_dir() -> str:
    """Returns the absolute path to the data sources directory."""
    return os.path.join(PROJECT_ROOT, DATA_SOURCES_DIR)


def get_novel_path(safe_file: str) -> str:
    """Returns the absolute path to a novel file."""
    return os.path.join(get_novels_dir(), safe_file)


def get_source_path(safe_file: str) -> str:
    """Returns the absolute path to a setting source file."""
    return os.path.join(get_sources_dir(), safe_file)


def get_history_dir(output_dir: str) -> str:
    """Returns the history directory path for a given output directory."""
    return os.path.join(output_dir, "history")


def get_version_dir(output_dir: str, version: str) -> str:
    """Returns the directory path for a specific review version."""
    return os.path.join(get_history_dir(output_dir), version)


def get_plot_findings_yaml_path(output_dir: str, basename: str) -> str:
    """Returns the path for the integrated plot findings YAML."""
    return os.path.join(output_dir, f"{basename}_plot_findings.yaml")


def get_plot_report_md_path(output_dir: str, basename: str) -> str:
    """Returns the path for the final plot Markdown report."""
    return os.path.join(output_dir, f"{basename}_plot_report.md")


def get_stopwords_path() -> str:
    """Returns the path to the stopwords JSON file."""
    return os.path.join(SCRIPT_DIR, "resources", "stopwords.json")


def get_src_path(relative_path: str) -> str:
    """Returns the absolute path to a file inside the src directory."""
    return os.path.join(PROJECT_ROOT, "src", relative_path)


def get_skills_dir() -> str:
    """Returns the absolute path to the skills directory."""
    return os.path.join(PROJECT_ROOT, "skills")


def get_templates_dir() -> str:
    """Returns the absolute path to the templates directory."""
    return os.path.join(PROJECT_ROOT, "src", "templates")
