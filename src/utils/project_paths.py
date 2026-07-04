import os

# Project Directory Constants (Default values, will be updated dynamically)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

NOVELS_DIR = "novels"
DATA_DIR = "data"
SOURCES_DIR = "sources"
DATA_SOURCES_DIR = os.path.join(DATA_DIR, SOURCES_DIR)

DEFAULT_RESULTS_DIR = "reviews"
DEFAULT_LOGS_DIR = "logs"


def update_constants(novels: str, data: str, sources: str, results: str) -> None:
    """Updates module-level constants dynamically when configuration changes."""
    global NOVELS_DIR, DATA_DIR, SOURCES_DIR, DATA_SOURCES_DIR, DEFAULT_RESULTS_DIR
    NOVELS_DIR = novels
    DATA_DIR = data
    SOURCES_DIR = sources
    DATA_SOURCES_DIR = os.path.join(data, sources)
    DEFAULT_RESULTS_DIR = results


# Naming Templates
FORMATTED_DRAFT_TEMPLATE = "{basename}_formatted.txt"
FINDINGS_YAML_TEMPLATE = "{basename}_findings.yaml"
REPORT_MD_TEMPLATE = "{basename}_report.md"
PLOT_FINDINGS_YAML_TEMPLATE = "{basename}_plot_findings.yaml"
PLOT_REPORT_MD_TEMPLATE = "{basename}_plot_report.md"


def get_output_dir(basename: str, results_dir: str | None = None) -> str:
    """Returns the output directory path for a given novel basename."""
    if results_dir is None:
        from src.utils.project_config import load_project_config

        try:
            config = load_project_config()
            results_dir = config.project.novel.results_dir
        except Exception:
            results_dir = DEFAULT_RESULTS_DIR
    return os.path.join(results_dir, basename)


def get_formatted_draft_path(output_dir: str, basename: str) -> str:
    """Returns the standard path for the formatted draft text."""
    return os.path.join(output_dir, FORMATTED_DRAFT_TEMPLATE.format(basename=basename))


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
    return os.path.join(output_dir, FINDINGS_YAML_TEMPLATE.format(basename=basename))


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
    return os.path.join(output_dir, REPORT_MD_TEMPLATE.format(basename=basename))


def get_novels_dir() -> str:
    """Returns the absolute path to the novels directory."""
    from src.utils.project_config import load_project_config

    try:
        config = load_project_config()
        novels = config.project.novel.novels_dir
    except Exception:
        novels = NOVELS_DIR
    return os.path.join(PROJECT_ROOT, novels)


def get_sources_dir() -> str:
    """Returns the absolute path to the data sources directory."""
    from src.utils.project_config import load_project_config

    try:
        config = load_project_config()
        data = config.project.novel.data_dir
        sources = config.project.novel.sources_dir
    except Exception:
        data = DATA_DIR
        sources = SOURCES_DIR
    return os.path.join(PROJECT_ROOT, data, sources)


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
    return os.path.join(
        output_dir, PLOT_FINDINGS_YAML_TEMPLATE.format(basename=basename)
    )


def get_plot_report_md_path(output_dir: str, basename: str) -> str:
    """Returns the path for the final plot Markdown report."""
    return os.path.join(output_dir, PLOT_REPORT_MD_TEMPLATE.format(basename=basename))


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


# Pipeline File Constants
FILTERED_CONTEXT_NAME = "01_filtered_context.txt"

TEXT_REVIEW_SKILLS = {
    "text-reviewer-logic": "02_logic_consistency.yaml",
    "text-reviewer-style": "03_style_expression.yaml",
}

PLOT_REVIEW_SKILLS = {
    "plot-reviewer-conflict": "02_plot_conflict.yaml",
    "plot-reviewer-structure": "03_plot_structure.yaml",
}


def get_filtered_context_path(output_dir: str) -> str:
    """Returns the path to the filtered context file."""
    return os.path.join(output_dir, FILTERED_CONTEXT_NAME)
