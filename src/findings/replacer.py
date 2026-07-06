import re

from src.utils.ai_client import AgyClientError
from src.utils.ai_task import BlockReplacementInput, BlockReplacementTask
from src.utils.logger import get_logger

logger = get_logger(__name__)


def extract_suggestion_candidate(suggestion):
    """
    Attempts to extract a replacement candidate enclosed in quotes from the suggestion.
    e.g., 「修正後のテキスト」 or （例：「〜」）
    """
    # Look for text inside Japanese quotes 「...」
    matches = re.findall(r"「([^」]+)」", suggestion)
    if matches:
        # If there are multiple, prefer the longer one or the last one if it looks like a full sentence.
        # But generally, if there is at least one, we can return it as a candidate.
        return matches[-1]  # Usually the example is at the end
    return None


def apply_fallback_to_block(context_lines, findings_in_block):
    """
    Fallback replacement logic when LLM is unavailable.
    Replaces originals with extracted suggestions inside context_lines.
    Returns (modified_block_text, success_findings, failed_findings)
    """
    modified_block_text = "".join(context_lines)
    success_findings = []
    failed_findings = []

    for f in findings_in_block:
        original = f.get("original", "").strip()
        suggestion = f.get("suggestion", "").strip()
        replacement = extract_suggestion_candidate(suggestion)

        if not replacement:
            failed_findings.append(
                (
                    f,
                    "Could not extract replacement text from suggestion. Manual intervention required.",
                )
            )
            continue

        # 1. Exact match
        if original in modified_block_text:
            modified_block_text = modified_block_text.replace(original, replacement, 1)
            success_findings.append((f, replacement, "extracted"))
            continue

        # 2. Fuzzy match with space/newline tolerance
        def clean_spacing(t):
            return re.sub(r"\s+", "", t)

        clean_original = clean_spacing(original)
        clean_block = clean_spacing(modified_block_text)

        if clean_original in clean_block:
            escaped_chars = [re.escape(c) for c in original if not c.isspace()]
            pattern_str = r"[\s\u3000]*".join(escaped_chars)
            match = re.search(pattern_str, modified_block_text)
            if match:
                matched_text = match.group(0)
                modified_block_text = modified_block_text.replace(
                    matched_text, replacement, 1
                )
                success_findings.append((f, replacement, "fuzzy"))
                continue

        failed_findings.append((f, f"Could not find original text: '{original}'"))

    return modified_block_text, success_findings, failed_findings


def query_llm_for_block_replacement(context_lines, findings_in_block, model):
    """
    Uses BlockReplacementTask to generate the rewritten block based on context and multiple findings.
    """
    task = BlockReplacementTask(model=model)
    input_data = BlockReplacementInput(
        context_lines=context_lines, findings_in_block=findings_in_block
    )
    try:
        result = task.execute(input_data)
        if result is None:
            logger.warning("LLM output was rejected (too short or failed validation).")
        return result
    except AgyClientError as e:
        logger.error(
            f"AgyClient failed with error during block replacement: {e}", exc_info=True
        )
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error calling AgyClient during block replacement: {e}",
            exc_info=True,
        )
        return None


def query_llm_for_single_replacement(context_lines, finding, model):
    """
    Uses BlockReplacementTask to generate the rewritten block based on context and a single finding.
    """
    task = BlockReplacementTask(model=model)
    input_data = BlockReplacementInput(
        context_lines=context_lines, findings_in_block=[finding]
    )
    try:
        result = task.execute(input_data)
        if result is None:
            logger.warning(
                f"LLM output was rejected for single finding {finding.get('id')}."
            )
        return result
    except AgyClientError as e:
        logger.error(
            f"AgyClient failed with error during single replacement ({finding.get('id')}): {e}",
            exc_info=True,
        )
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error calling AgyClient during single replacement ({finding.get('id')}): {e}",
            exc_info=True,
        )
        return None


def apply_fallback_to_single_finding(context_lines, finding):
    """
    Applies rule-based fallback replacement to a single finding.
    Returns (success, result_block_text, status_message).
    """
    original = finding.get("original", "").strip()
    suggestion = finding.get("suggestion", "").strip()
    replacement = extract_suggestion_candidate(suggestion)

    if not replacement:
        return (
            False,
            "".join(context_lines),
            "Could not extract replacement text from suggestion.",
        )

    block_text = "".join(context_lines)

    # 1. Exact match
    if original in block_text:
        new_text = block_text.replace(original, replacement, 1)
        return True, new_text, "extracted"

    # 2. Fuzzy match with space/newline tolerance
    def clean_spacing(t):
        return re.sub(r"\s+", "", t)

    clean_original = clean_spacing(original)
    clean_block = clean_spacing(block_text)

    if clean_original in clean_block:
        escaped_chars = [re.escape(c) for c in original if not c.isspace()]
        # Matches matching characters with optional fullwidth/halfwidth spaces or newlines in between
        pattern_str = r"[\s\u3000]*".join(escaped_chars)
        match = re.search(pattern_str, block_text)
        if match:
            matched_text = match.group(0)
            new_text = block_text.replace(matched_text, replacement, 1)
            return True, new_text, "fuzzy"

    return False, block_text, f"Could not find original text: '{original}'"


def print_finding_diff(finding):
    """
    Logs a formatted summary of the finding.
    """
    lines = [
        "-" * 60,
        f"ID      : {finding.get('id', 'N/A')}",
        f"場所    : {finding.get('location', 'N/A')}",
        f"カテゴリ: {finding.get('category', 'N/A')} (重要度: {finding.get('severity', 'N/A')})",
        f"分析    : {finding.get('analysis', 'N/A')}",
        f"原文    : \033[31m{finding.get('original', 'N/A')}\033[0m",
        f"修正案  : \033[32m{finding.get('suggestion', 'N/A')}\033[0m",
        "-" * 60,
    ]
    logger.info("\n" + "\n".join(lines))
