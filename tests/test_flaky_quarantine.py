from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.utils.flaky_quarantine import load_quarantined_node_ids, mark_flaky_items


class TestLoadQuarantinedNodeIds:
    def test_reads_node_ids_from_yaml_list(self, tmp_path):
        path = tmp_path / "flaky_quarantine.yaml"
        path.write_text(
            "tests:\n"
            "  - tests/test_foo.py::test_bar\n"
            "  - tests/test_foo.py::test_baz\n",
            encoding="utf-8",
        )
        assert load_quarantined_node_ids(path) == {
            "tests/test_foo.py::test_bar",
            "tests/test_foo.py::test_baz",
        }

    def test_missing_file_returns_empty_set(self, tmp_path):
        assert load_quarantined_node_ids(tmp_path / "does_not_exist.yaml") == set()

    def test_empty_tests_list_returns_empty_set(self, tmp_path):
        path = tmp_path / "flaky_quarantine.yaml"
        path.write_text("tests: []\n", encoding="utf-8")
        assert load_quarantined_node_ids(path) == set()

    def test_missing_tests_key_returns_empty_set(self, tmp_path):
        path = tmp_path / "flaky_quarantine.yaml"
        path.write_text("# no tests key here\n", encoding="utf-8")
        assert load_quarantined_node_ids(path) == set()


class TestMarkFlakyItems:
    def test_marks_only_quarantined_items(self):
        quarantined_id = "tests/test_foo.py::test_bar"
        item_quarantined = MagicMock(nodeid=quarantined_id)
        item_other = MagicMock(nodeid="tests/test_foo.py::test_other")

        mark_flaky_items([item_quarantined, item_other], {quarantined_id})

        item_quarantined.add_marker.assert_called_once()
        marker = item_quarantined.add_marker.call_args.args[0]
        assert marker.name == "flaky"
        assert marker.kwargs == {"reruns": 3, "reruns_delay": 1}
        item_other.add_marker.assert_not_called()

    def test_respects_custom_reruns_and_delay(self):
        quarantined_id = "tests/test_foo.py::test_bar"
        item = MagicMock(nodeid=quarantined_id)

        mark_flaky_items([item], {quarantined_id}, reruns=5, reruns_delay=2)

        marker = item.add_marker.call_args.args[0]
        assert marker.kwargs == {"reruns": 5, "reruns_delay": 2}

    def test_noop_when_no_quarantined_ids(self):
        item = MagicMock(nodeid="tests/test_foo.py::test_bar")
        mark_flaky_items([item], set())
        item.add_marker.assert_not_called()


def test_pytest_mark_flaky_marker_is_available():
    # pytest-rerunfailuresが提供する`flaky`マーカーが実際に利用可能であることを確認。
    marker = pytest.mark.flaky(reruns=3, reruns_delay=1)
    assert marker.name == "flaky"
