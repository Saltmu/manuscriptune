import json
import math
import os
import re
import sys

from src.utils import project_config as writer_helper
from src.utils import project_paths


# Load stopwords from external resource file
def _load_stopwords() -> set[str]:
    stopwords_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "utils", "resources", "stopwords.json")
    )
    try:
        with open(stopwords_path, encoding="utf-8") as f:
            words = json.load(f)
            return set(words)
    except Exception as e:
        print(
            f"Warning: Failed to load stopwords from {stopwords_path}: {e}",
            file=sys.stderr,
        )
        return set()


STOPWORDS = _load_stopwords()


def extract_entities_from_sources(sources_dir):
    """
    Extracts important entities (character names, key terms with rubies, terms in brackets)
    from setting files to create a high-priority entity dictionary.
    """
    entities = set()
    if not os.path.exists(sources_dir):
        return entities

    # Add main characters from project config
    main_chars = writer_helper.get_novel_setting("main_characters", [])
    entities.update(main_chars)

    ruby_pattern = re.compile(r"([一-龠ぁ-んァ-ヴー]{2,15})（([ァ-ヴーa-zA-Z\s・]+)）")
    bracket_pattern = re.compile(r"『([^』]{2,15})』")
    char_pattern = re.compile(r"^([^\n\(\s【]{2,10})\s*\([a-zA-Z\s]+\)", re.MULTILINE)

    for filename in os.listdir(sources_dir):
        if not filename.endswith(".txt"):
            continue
        file_path = os.path.join(sources_dir, filename)
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # 1. Extract ruby bases and reading text
            for match in ruby_pattern.finditer(content):
                entities.add(match.group(1))  # Parent word (e.g. 大調律圏)
                entities.add(
                    match.group(2)
                )  # Ruby reading (e.g. ザ・グランド・テンプラメント)

            # 2. Extract words in Japanese double brackets (e.g. 『二つの色とエネルギー』)
            for match in bracket_pattern.finditer(content):
                entities.add(match.group(1))

            # 3. Extract character names from character overview files
            if "キャラクター" in filename:
                for match in char_pattern.finditer(content):
                    name = match.group(1).strip()
                    if name and len(name) >= 2:
                        entities.add(name)
        except Exception as e:
            print(
                f"Warning: Failed to parse entity from {filename}: {e}", file=sys.stderr
            )

    # Filter out stopwords or empty strings
    entities = {e for e in entities if e and e not in STOPWORDS and len(e) >= 2}
    return entities


def extract_keywords_from_novel(text):
    """
    Extracts potential search keywords (Katakana and Kanji words) from the novel draft,
    excluding common stopwords.
    """
    katakana_pat = re.compile(r"[ァ-ヴー]{2,}")
    kanji_pat = re.compile(r"[一-龠]{2,}")

    keywords = set()
    keywords.update(katakana_pat.findall(text))
    keywords.update(kanji_pat.findall(text))

    # Filter out stopwords and short terms
    filtered = {kw for kw in keywords if len(kw) >= 2 and kw not in STOPWORDS}
    return filtered


# Keywords to identify basic contexts (e.g. timelines, core worldview rules)
BASIC_CONTEXT_KEYWORDS = [
    "年表",
    "歴史",
    "基本ルール",
    "物理法則",
    "魔力体系",
    "世界観",
    "タイムライン",
    "timeline",
    "history",
    "rule",
    "system",
]


def is_basic_context_file(filename: str) -> bool:
    """
    Checks if the given filename corresponds to a basic context file
    (e.g., timeline, core rules) that should be prioritized and kept whole.
    """
    name_lower = filename.lower()
    return any(keyword in name_lower for keyword in BASIC_CONTEXT_KEYWORDS)


def split_into_sections(content: str) -> list[str]:
    """
    Splits the text into logical sections based on Markdown headers (#, ##, ###)
    or specific block markers (like ■, ◆, ▲, ●, ★, ▼).
    """
    # Match Markdown headers or common Japanese block markers at the start of a line
    header_pattern = re.compile(r"^(?:#{1,6}\s+|[■◆▲●★▼])", re.MULTILINE)

    sections = []
    matches = list(header_pattern.finditer(content))

    if not matches:
        # Fallback to double newlines if no headers or markers are found
        raw_chunks = re.split(r"\n\s*\n", content)
        return [c.strip() for c in raw_chunks if c.strip()]

    # If there is content before the first header, add it
    first_match_start = matches[0].start()
    pre_content = content[:first_match_start].strip()
    if pre_content:
        for part in re.split(r"\n\s*\n", pre_content):
            if part.strip():
                sections.append(part.strip())

    # Extract sections starting with each header
    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_content = content[start:end].strip()
        if section_content:
            sections.append(section_content)

    return sections


def _collect_raw_chunks(sources_dir: str) -> tuple[list[dict], list[tuple]]:
    """
    Scans the sources directory and collects basic contexts and split chunks.
    """
    source_files = [f for f in os.listdir(sources_dir) if f.endswith(".txt")]
    raw_chunks_all = []
    basic_contexts = []

    for filename in source_files:
        file_path = os.path.join(sources_dir, filename)
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        if is_basic_context_file(filename):
            content_str = content.strip()
            if content_str:
                basic_contexts.append(
                    {
                        "file": filename,
                        "text": content_str,
                    }
                )
                raw_chunks_all.append((filename, 0, content_str))
        else:
            raw_chunks = split_into_sections(content)
            for i, raw_chunk in enumerate(raw_chunks):
                chunk_text = raw_chunk.strip()
                if not chunk_text:
                    continue
                raw_chunks_all.append((filename, i, chunk_text))

    return basic_contexts, raw_chunks_all


def _calculate_word_weights(
    novel_keywords: set[str], entity_words: set[str], raw_chunks_all: list
) -> dict[str, float]:
    """
    Calculates weights for each keyword using an IDF-like metric.
    """
    total_chunks = len(raw_chunks_all)
    word_weights = {}

    for kw in novel_keywords:
        df = sum(1 for _, _, text in raw_chunks_all if kw in text)
        idf = math.log(total_chunks / (df + 1)) + 1.0

        base_weight = 10.0 if kw in entity_words else 1.0
        word_weights[kw] = base_weight * idf

    return word_weights


def _score_and_sort_chunks(
    raw_chunks_all: list, novel_keywords: set[str], word_weights: dict[str, float]
) -> list[dict]:
    """
    Scores each chunk based on the keywords it contains and sorts them in descending order.
    """
    all_chunks = []
    for filename, idx, chunk_text in raw_chunks_all:
        score = 0.0
        matched_kws = []
        for kw in novel_keywords:
            if kw in chunk_text:
                count = chunk_text.count(kw)
                score += count * word_weights[kw]
                matched_kws.append(kw)

        if score > 0:
            all_chunks.append(
                {
                    "file": filename,
                    "index": idx,
                    "text": chunk_text,
                    "score": score,
                    "matches": matched_kws,
                }
            )

    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    return all_chunks


def _select_and_format_context(
    basic_contexts: list[dict], all_chunks: list[dict], max_chars: int
) -> tuple[str, list[dict], int]:
    """
    Selects top chunks up to the character limit and formats the output content.
    """
    selected_chunks: list[dict] = []
    output_content = "=== FILTERED SETTING CONTEXT ===\n"
    output_content += "This file contains automatically filtered relevant settings based on keywords in the chapter.\n\n"

    # Prioritize basic contexts (timelines, rules, etc.)
    if basic_contexts:
        output_content += "=== BASIC CONTEXTS (PRIORITIZED & UNFRAGMENTED) ===\n"
        for bc in basic_contexts:
            chunk_header = f"--- Source: {bc['file']} (Basic Context) ---\n"
            chunk_body = bc["text"] + "\n\n"
            chunk_full = chunk_header + chunk_body

            if len(output_content) + len(chunk_full) > max_chars:
                output_content += (
                    chunk_header
                    + chunk_body[: max_chars - len(output_content) - len(chunk_header)]
                    + "... (truncated)\n"
                )
                break
            output_content += chunk_full

    current_length = len(output_content)
    added_files = {bc["file"] for bc in basic_contexts}

    # Add other chunks
    for chunk in all_chunks:
        if chunk["file"] in added_files:
            continue

        chunk_header = f"--- Source: {chunk['file']} (Section {chunk['index']}, Score: {chunk['score']:.1f}) ---\n"
        chunk_body = chunk["text"] + "\n\n"
        chunk_full = chunk_header + chunk_body

        if current_length + len(chunk_full) > max_chars:
            if not selected_chunks and current_length < max_chars:
                output_content += (
                    chunk_header
                    + chunk_body[: max_chars - current_length - len(chunk_header)]
                    + "... (truncated)\n"
                )
            break

        selected_chunks.append(chunk)
        output_content += chunk_full
        current_length += len(chunk_full)

    return output_content, selected_chunks, current_length


def main():
    if len(sys.argv) < 3:
        print("Usage: python filter_context.py [NOVEL_PATH] [OUTPUT_PATH]")
        sys.exit(1)

    novel_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.exists(novel_path):
        print(f"Error: Novel file {novel_path} not found.")
        sys.exit(1)

    # Find sources directory
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources_dir = os.path.join(root_dir, project_paths.DATA_SOURCES_DIR)

    if not os.path.exists(sources_dir):
        print(
            f"Error: Sources directory {sources_dir} not found. Please run sync_gdrive.py first."
        )
        sys.exit(1)

    # 1. Build Entity Dictionary from setting sources
    entity_words = extract_entities_from_sources(sources_dir)
    print(f"Extracted {len(entity_words)} high-priority entities from sources.")

    # 2. Read novel text and extract keywords
    with open(novel_path, encoding="utf-8") as f:
        novel_text = f.read()

    novel_keywords = extract_keywords_from_novel(novel_text)
    print(f"Extracted {len(novel_keywords)} valid keywords from novel.")

    # 3. Collect chunks
    basic_contexts, raw_chunks_all = _collect_raw_chunks(sources_dir)

    # 4. Calculate word weights
    word_weights = _calculate_word_weights(novel_keywords, entity_words, raw_chunks_all)

    # 5. Score and sort chunks
    all_chunks = _score_and_sort_chunks(raw_chunks_all, novel_keywords, word_weights)

    # 6. Select chunks and format output
    MAX_CHARS = 20000
    output_content, selected_chunks, current_length = _select_and_format_context(
        basic_contexts, all_chunks, MAX_CHARS
    )

    # Ensure directory of output path exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(
        f"Saved filtered context ({current_length} chars, {len(selected_chunks)} chunks) to {output_path}"
    )


if __name__ == "__main__":
    main()
