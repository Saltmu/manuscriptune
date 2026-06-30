import difflib
import re


def parse_line_number(location_str):
    """
    Parses line number from location string like "8行目" or "15".
    Returns 1-based index or None.
    """
    if not location_str:
        return None
    match = re.search(r"(\d+)", str(location_str))
    if match:
        return int(match.group(1))
    return None


def find_target_line(text_lines, finding):
    """
    Finds the 1-based line number in text_lines where finding's original text exists.
    Looks near specified location first, then falls back to full scan.
    Returns 1-based index or None.
    """
    original = finding.get("original", "").strip().replace("\r\n", "\n")
    if not original:
        return None

    # 1. Exact match check
    line_no = _find_exact_match(text_lines, original, finding)
    if line_no is not None:
        return line_no

    # 2. Near location check
    line_no = _find_near_location(text_lines, original, finding)
    if line_no is not None:
        return line_no

    # 3. Fuzzy match check
    line_no = _find_fuzzy_match(text_lines, original, finding)
    if line_no is not None:
        return line_no

    # 4. Sub-original split match
    line_no = _find_sub_original_matches(text_lines, original, finding)
    if line_no is not None:
        return line_no

    return None


def _find_exact_match(text_lines, original, finding):
    raw_text = "".join(text_lines).replace("\r\n", "\n")
    if original in raw_text:
        offset = raw_text.find(original)
        line_no = raw_text[:offset].count("\n") + 1
        matched_count = original.count("\n") + 1
        finding["_matched_lines"] = list(range(line_no, line_no + matched_count))
        return line_no
    return None


def _find_near_location(text_lines, original, finding):
    location_str = finding.get("location", "")
    line_no = parse_line_number(location_str)

    if line_no is not None:
        target_idx = line_no - 1
        for idx in range(target_idx - 5, target_idx + 6):
            if 0 <= idx < len(text_lines):
                normalized_line = text_lines[idx].replace("\r\n", "\n").strip()
                if original in normalized_line:
                    finding["_matched_lines"] = [idx + 1]
                    return idx + 1

    for idx, line in enumerate(text_lines):
        normalized_line = line.replace("\r\n", "\n").strip()
        if original in normalized_line:
            finding["_matched_lines"] = [idx + 1]
            return idx + 1
    return None


def _find_fuzzy_match(text_lines, original, finding):
    raw_text = "".join(text_lines).replace("\r\n", "\n")

    def clean_spacing(text):
        return re.sub(r"\s+", "", text)

    clean_original = clean_spacing(original)
    if clean_original:
        clean_raw = clean_spacing(raw_text)
        if clean_original in clean_raw:
            start_char_idx = clean_raw.find(clean_original)
            char_count = 0
            for idx, line in enumerate(text_lines):
                char_count += len(clean_spacing(line))
                if char_count > start_char_idx:
                    finding["_matched_lines"] = [idx + 1]
                    return idx + 1
    return None


def _find_sub_original_matches(text_lines, original, finding):
    raw_text = "".join(text_lines).replace("\r\n", "\n")

    def clean_spacing(text):
        return re.sub(r"\s+", "", text)

    sub_originals = [s.strip() for s in original.split("\n") if s.strip()]
    if not sub_originals:
        return None

    matched_lines = []

    for sub in sub_originals:
        sub_clean = clean_spacing(sub)
        if not sub_clean:
            continue

        _match_single_sub(
            text_lines, raw_text, sub, sub_clean, matched_lines, difflib, clean_spacing
        )

    if matched_lines:
        unique_matched = sorted(list(set(matched_lines)))
        finding["_matched_lines"] = unique_matched
        return unique_matched[0]

    return None


def _match_single_sub(
    text_lines, raw_text, sub, sub_clean, matched_lines, difflib, clean_spacing
):
    # 1. Exact match scan in raw text
    if sub in raw_text:
        offset = raw_text.find(sub)
        lno = raw_text[:offset].count("\n") + 1
        matched_lines.append(lno)
        return True

    # 2. Line-by-line simple match
    for idx, line in enumerate(text_lines):
        normalized_line = line.replace("\r\n", "\n").strip()
        if sub in normalized_line:
            matched_lines.append(idx + 1)
            return True

    # 3. Clean spacing match
    for idx, line in enumerate(text_lines):
        if sub_clean in clean_spacing(line):
            matched_lines.append(idx + 1)
            return True

    # 4. SequenceMatcher similarity match (threshold 0.85)
    best_idx = -1
    best_ratio = 0.0
    for idx, line in enumerate(text_lines):
        line_clean = clean_spacing(line)
        if not line_clean:
            continue
        if (
            abs(len(sub_clean) - len(line_clean))
            > max(len(sub_clean), len(line_clean)) * 0.5
        ):
            continue
        ratio = difflib.SequenceMatcher(None, sub_clean, line_clean).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = idx

    if best_ratio >= 0.85 and best_idx != -1:
        matched_lines.append(best_idx + 1)
        return True

    return False
