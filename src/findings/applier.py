import argparse
import os
import shutil

from src.findings.replacer import (
    apply_fallback_to_block,
    apply_fallback_to_single_finding,
    extract_suggestion_candidate,
    print_finding_diff,
    query_llm_for_block_replacement,
    query_llm_for_single_replacement,
)
from src.findings.text_matcher import find_target_line
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

logger = get_logger(__name__)


def write_file(filepath, content):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def _interactive_choice(finding: dict) -> str:
    """
    Prompts the user for a single finding and sets its accepted state.
    """
    print_finding_diff(finding)
    candidate = extract_suggestion_candidate(finding.get("suggestion", ""))
    if candidate:
        logger.info(f"(抽出された簡易修正案候補: 「{candidate}」)")

    choice = (
        input(
            "この指摘を適用しますか？ [y:はい / n:いいえ / e:手動入力 / a:以降すべて適用 / q:終了して適用開始]: "
        )
        .strip()
        .lower()
    )

    if choice == "y":
        finding["accepted"] = "y"
    elif choice == "e":
        custom_replacement = input(
            "適用する修正後のテキストを入力してください: "
        ).strip()
        finding["suggestion"] = f"「{custom_replacement}」に修正してください。"
        finding["accepted"] = "y"

    return choice


def _apply_all_remaining(
    findings: list[dict],
    start_idx: int,
    accepted_ids: set[str],
    args: argparse.Namespace,
) -> None:
    """
    Sets accepted status for all remaining findings.
    """
    for remain_f in findings[start_idx:]:
        remain_fid = remain_f.get("id")
        if args.accept_ids:
            remain_f["accepted"] = "y" if remain_fid in accepted_ids else "n"
        else:
            remain_f["accepted"] = "y"


def _determine_accepted_findings_auto(
    findings: list[dict], accepted_ids: set[str], args: argparse.Namespace
) -> None:
    """
    Sets accepted status automatically based on accept_ids or auto flags.
    """
    for f in findings:
        fid = f.get("id")
        if args.accept_ids:
            f["accepted"] = "y" if fid in accepted_ids else "n"
        elif args.auto:
            if f.get("accepted") != "y":
                f["accepted"] = "n"


def _determine_accepted_findings_interactive(
    findings: list[dict], accepted_ids: set[str], args: argparse.Namespace
) -> None:
    """
    Queries the user interactively for each finding's accepted state.
    """
    for i, finding in enumerate(findings):
        choice = _interactive_choice(finding)

        if choice == "a":
            finding["accepted"] = "y"
            _apply_all_remaining(findings, i + 1, accepted_ids, args)
            args.interactive = False
            args.auto = True
            break
        elif choice == "q":
            logger.info("適用処理を終了し、これまでに確定した変更を適用します。")
            break
        elif choice not in ("y", "e"):
            finding["accepted"] = "n"


def _determine_accepted_findings(
    findings: list[dict], text_lines: list[str], args: argparse.Namespace
) -> list[tuple[int, dict]]:
    accepted_ids = set()
    if args.accept_ids:
        accepted_ids = {x.strip() for x in args.accept_ids.split(",")}

    for f in findings:
        if "accepted" not in f:
            f["accepted"] = None

    if args.accept_ids or args.auto:
        _determine_accepted_findings_auto(findings, accepted_ids, args)
    else:
        _determine_accepted_findings_interactive(findings, accepted_ids, args)

    active_findings = []
    for f in findings:
        fid = f.get("id")
        if f.get("accepted") == "y":
            line_no = find_target_line(text_lines, f)
            if line_no is not None:
                active_findings.append((line_no, f))
            else:
                logger.error(
                    f"[FAIL] {fid} の適用に失敗しました: 原文が見つかりません。"
                )
                f["apply_status"] = "failed"
                f["apply_result"] = "原文が見つかりませんでした。"
        else:
            f["apply_status"] = None
            f["apply_result"] = None

    return active_findings


def _group_findings(
    active_findings: list[tuple[int, dict]],
) -> list[list[tuple[int, dict]]]:
    active_findings.sort(key=lambda x: x[0])
    groups = []
    if active_findings:
        current_group = [active_findings[0]]
        for item in active_findings[1:]:
            last_line_no = current_group[-1][0]
            curr_line_no = item[0]
            if curr_line_no - last_line_no <= 5:
                current_group.append(item)
            else:
                groups.append(current_group)
                current_group = [item]
        groups.append(current_group)

    groups.sort(key=lambda g: g[0][0], reverse=True)
    return groups


def _apply_single_group_bulk(
    text_lines: list[str],
    group: list[tuple[int, dict]],
    args: argparse.Namespace,
    context_lines: list[str],
    start_idx: int,
    end_idx: int,
) -> tuple[bool, int]:
    """
    Attempts bulk block replacement using LLM.
    Returns (success_boolean, applied_count).
    """
    findings_in_block = [item[1] for item in group]
    result_block_text = query_llm_for_block_replacement(
        context_lines, findings_in_block, args.model
    )
    if not result_block_text:
        return False, 0

    if not result_block_text.endswith("\n") and len(result_block_text) > 0:
        result_block_text += "\n"

    text_lines[start_idx:end_idx] = result_block_text.splitlines(keepends=True)

    applied_count = 0
    for f in findings_in_block:
        fid = f.get("id")
        logger.info(f"[SUCCESS] {fid} を適用しました (LLMコンテキスト一括方式)。")
        applied_count += 1
        f["apply_status"] = "success"
        f["apply_result"] = "LLMコンテキスト一括方式"

    return True, applied_count


def _apply_single_group_fallback_bulk(
    text_lines: list[str],
    group: list[tuple[int, dict]],
    context_lines: list[str],
    start_idx: int,
    end_idx: int,
) -> tuple[int, int]:
    """
    Applies bulk fallback replacement.
    """
    findings_in_block = [item[1] for item in group]
    result_block_text, success_findings, failed_findings = apply_fallback_to_block(
        context_lines, findings_in_block
    )
    if not result_block_text.endswith("\n") and len(result_block_text) > 0:
        result_block_text += "\n"

    text_lines[start_idx:end_idx] = result_block_text.splitlines(keepends=True)

    applied_count = 0
    failed_count = 0
    for f, replacement, m in success_findings:
        fid = f.get("id")
        logger.info(f"[SUCCESS] {fid} を適用しました (フォールバック・{m}方式)。")
        applied_count += 1
        f["apply_status"] = "success"
        f["apply_result"] = f"フォールバック({m}方式): {replacement}"

    for f, error_msg in failed_findings:
        fid = f.get("id")
        logger.error(f"[FAIL] {fid} の適用に失敗しました: {error_msg}")
        failed_count += 1
        f["apply_status"] = "failed"
        f["apply_result"] = error_msg

    return applied_count, failed_count


def _apply_single_finding_sequential(
    text_lines: list[str],
    f: dict,
    args: argparse.Namespace,
    C: int,
) -> tuple[int, int]:
    """
    Applies a single finding sequentially using LLM or rule-based fallback.
    Returns (applied_count, failed_count).
    """
    fid = f.get("id")
    curr_line_no = find_target_line(text_lines, f)
    if curr_line_no is None:
        logger.error(f"[FAIL] {fid} の適用に失敗しました: 原文が見つかりません。")
        f["apply_status"] = "failed"
        f["apply_result"] = "原文が見つかりませんでした。"
        return 0, 1

    line_nos = [curr_line_no]
    if "_matched_lines" in f:
        line_nos.extend(f["_matched_lines"])
    curr_L_min = min(line_nos)
    curr_L_max = max(line_nos)

    curr_start_idx = max(0, curr_L_min - 1 - C)
    curr_end_idx = min(len(text_lines), curr_L_max + C)
    curr_context_lines = text_lines[curr_start_idx:curr_end_idx]

    single_success = False
    single_result_block_text = None

    if not args.no_llm:
        single_result_block_text = query_llm_for_single_replacement(
            curr_context_lines, f, args.model
        )
        if single_result_block_text:
            single_success = True

    if single_success and single_result_block_text:
        if (
            not single_result_block_text.endswith("\n")
            and len(single_result_block_text) > 0
        ):
            single_result_block_text += "\n"

        text_lines[curr_start_idx:curr_end_idx] = single_result_block_text.splitlines(
            keepends=True
        )
        logger.info(f"[SUCCESS] {fid} を適用しました (LLM個別方式)。")
        f["apply_status"] = "success"
        f["apply_result"] = "LLM個別方式"
        return 1, 0

    # Fallback to rule-based fuzzy replacement if LLM fails
    fb_success, fb_result_block, fb_msg = apply_fallback_to_single_finding(
        curr_context_lines, f
    )
    if fb_success:
        if not fb_result_block.endswith("\n") and len(fb_result_block) > 0:
            fb_result_block += "\n"

        text_lines[curr_start_idx:curr_end_idx] = fb_result_block.splitlines(
            keepends=True
        )
        logger.info(f"[SUCCESS] {fid} を適用しました (フォールバック・{fb_msg}方式)。")
        f["apply_status"] = "success"
        f["apply_result"] = f"フォールバック({fb_msg}方式)"
        return 1, 0
    else:
        logger.error(f"[FAIL] {fid} の適用に失敗しました: {fb_msg}")
        f["apply_status"] = "failed"
        f["apply_result"] = fb_msg
        return 0, 1


def _apply_single_group(
    text_lines: list[str],
    group: list[tuple[int, dict]],
    args: argparse.Namespace,
) -> tuple[int, int]:
    """
    Applies findings within a single group to text_lines.
    Returns (applied_count, failed_count).
    """
    line_nos = []
    for line_no, f in group:
        line_nos.append(line_no)
        if "_matched_lines" in f:
            line_nos.extend(f["_matched_lines"])
    L_min = min(line_nos)
    L_max = max(line_nos)

    C = 4
    start_idx = max(0, L_min - 1 - C)
    end_idx = min(len(text_lines), L_max + C)
    context_lines = text_lines[start_idx:end_idx]

    if not args.no_llm:
        success, app = _apply_single_group_bulk(
            text_lines, group, args, context_lines, start_idx, end_idx
        )
        if success:
            return app, 0

    if args.no_llm:
        return _apply_single_group_fallback_bulk(
            text_lines, group, context_lines, start_idx, end_idx
        )

    # Sequential retry loop for individual findings when bulk replacement fails
    applied_count = 0
    failed_count = 0
    sorted_group = sorted(group, key=lambda x: x[0], reverse=True)
    for line_no, f in sorted_group:
        app, fail = _apply_single_finding_sequential(text_lines, f, args, C)
        applied_count += app
        failed_count += fail

    return applied_count, failed_count


def _apply_grouped_findings(
    text_lines: list[str],
    groups: list[list[tuple[int, dict]]],
    args: argparse.Namespace,
) -> tuple[int, int]:
    applied_count = 0
    failed_count = 0

    for group in groups:
        app, fail = _apply_single_group(text_lines, group, args)
        applied_count += app
        failed_count += fail

    return applied_count, failed_count


def _save_outputs_and_print_summary(
    formatted_txt_path: str,
    findings_yaml_path: str,
    text_lines: list[str],
    findings: list[dict],
    stats: tuple[int, int, int],
) -> None:
    txt_bak = formatted_txt_path + ".bak"
    yaml_bak = findings_yaml_path + ".bak"

    txt_backed_up = False
    yaml_backed_up = False
    try:
        # Create backups
        if os.path.exists(formatted_txt_path):
            shutil.copy2(formatted_txt_path, txt_bak)
            txt_backed_up = True
        if os.path.exists(findings_yaml_path):
            shutil.copy2(findings_yaml_path, yaml_bak)
            yaml_backed_up = True

        # Write text file
        write_file(formatted_txt_path, "".join(text_lines))
        logger.info(f"小説テキストを更新しました: {formatted_txt_path}")

        # Write YAML file
        updated_yaml_data = {"findings": findings}
        YamlHandler.dump(updated_yaml_data, findings_yaml_path)
        logger.info(f"指摘YAMLを更新しました: {findings_yaml_path}")

        # Remove backups on success
        if txt_backed_up and os.path.exists(txt_bak):
            os.remove(txt_bak)
        if yaml_backed_up and os.path.exists(yaml_bak):
            os.remove(yaml_bak)

    except Exception as e:
        logger.error(
            f"保存処理中にエラーが発生しました。バックアップから復元します: {e}",
            exc_info=True,
        )
        # Restore from backups
        if txt_backed_up and os.path.exists(txt_bak):
            shutil.move(txt_bak, formatted_txt_path)
            logger.info("小説テキストをバックアップから復元しました。")
        if yaml_backed_up and os.path.exists(yaml_bak):
            shutil.move(yaml_bak, findings_yaml_path)
            logger.info("指摘YAMLをバックアップから復元しました。")
        raise e

    applied_count, skipped_count, failed_count = stats
    logger.info("=== 反映処理完了 ===")
    logger.info(
        f"適用: {applied_count} 件, スキップ: {skipped_count} 件, 失敗: {failed_count} 件"
    )
