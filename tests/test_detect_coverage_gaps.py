import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.utils.detect_coverage_gaps import (
    detect_gaps,
    format_missing_lines,
    generate_markdown,
    main,
)


def test_format_missing_lines():
    assert format_missing_lines([]) == ""
    assert format_missing_lines([5]) == "5"
    assert format_missing_lines([5, 6, 7]) == "5-7"
    assert format_missing_lines([5, 7, 8]) == "5, 7-8"
    assert format_missing_lines([1, 2, 4, 6, 7, 8, 10]) == "1-2, 4, 6-8, 10"


def test_generate_markdown():
    coverage_data = {
        "files": {
            "src/utils/detect_bloat.py": {
                "summary": {
                    "percent_covered": 83.33333333333333,
                },
                "missing_lines": [5, 6],
            },
            "src/utils/perfect.py": {
                "summary": {
                    "percent_covered": 100.0,
                },
                "missing_lines": [],
            },
        }
    }
    md = generate_markdown(coverage_data)
    assert "src/utils/detect_bloat.py" in md
    assert "83.33%" in md
    assert "5-6" in md
    assert "perfect.py" not in md


def test_generate_markdown_all_perfect():
    coverage_data = {
        "files": {
            "src/utils/perfect.py": {
                "summary": {
                    "percent_covered": 100.0,
                },
                "missing_lines": [],
            }
        }
    }
    md = generate_markdown(coverage_data)
    assert "All files have 100% test coverage!" in md


def test_detect_gaps_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "coverage.json")
        coverage_data = {
            "files": {
                "src/utils/detect_bloat.py": {
                    "summary": {
                        "percent_covered": 80.0,
                    },
                    "missing_lines": [10, 11, 12],
                }
            }
        }
        with open(json_path, "w") as f:
            json.dump(coverage_data, f)

        data = detect_gaps(json_path=json_path)
        assert "src/utils/detect_bloat.py" in data["files"]


def test_detect_gaps_run_coverage():
    coverage_data = {
        "files": {
            "test.py": {"summary": {"percent_covered": 90.0}, "missing_lines": [1]}
        }
    }

    with (
        patch("subprocess.run") as mock_run,
        patch("builtins.open", MagicMock()),
        patch("json.load") as mock_json_load,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        mock_json_load.return_value = coverage_data

        data = detect_gaps()
        assert "test.py" in data["files"]
        mock_run.assert_called_once()


def test_detect_gaps_run_coverage_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="Failed to generate json"
        )
        with pytest.raises(SystemExit):
            detect_gaps()


def test_main_stdout():
    coverage_data = {
        "files": {
            "src/utils/detect_bloat.py": {
                "summary": {
                    "percent_covered": 83.33,
                },
                "missing_lines": [5],
            }
        }
    }
    with (
        patch("src.utils.detect_coverage_gaps.detect_gaps", return_value=coverage_data),
        patch("sys.argv", ["detect-coverage-gaps"]),
        patch("builtins.print") as mock_print,
    ):
        main()
        mock_print.assert_any_call(generate_markdown(coverage_data))


def test_main_output_file():
    coverage_data = {
        "files": {
            "src/utils/detect_bloat.py": {
                "summary": {
                    "percent_covered": 83.33,
                },
                "missing_lines": [5],
            }
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "report.md")
        with (
            patch(
                "src.utils.detect_coverage_gaps.detect_gaps", return_value=coverage_data
            ),
            patch("sys.argv", ["detect-coverage-gaps", "--output", out_path]),
        ):
            main()
            assert os.path.exists(out_path)
            with open(out_path, encoding="utf-8") as f:
                content = f.read()
            assert "src/utils/detect_bloat.py" in content


def test_main_error_handling():
    with (
        patch(
            "src.utils.detect_coverage_gaps.detect_gaps",
            side_effect=Exception("Read error"),
        ),
        patch("sys.argv", ["detect-coverage-gaps"]),
    ):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1
