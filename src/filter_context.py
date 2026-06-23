import os
import re
import sys
import math

# Add skills/novel-writer to path to use writer_helper
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'skills', 'novel-writer')))
try:
    import writer_helper
except ImportError:
    writer_helper = None

# A set of common Japanese words to ignore as search keywords (Stopwords)
STOPWORDS = {
    "こと", "もの", "とき", "ため", "これ", "それ", "あれ", "どれ", "ここ", "そこ", "あそこ", "どこ",
    "自分", "彼ら", "彼女", "人間", "世界", "時間", "瞬間", "場所", "方法", "理由", "結果", "状態",
    "部分", "全体", "空気", "感覚", "意識", "存在", "言葉", "名前", "表情", "吐息", "沈黙", "視線",
    "呼吸", "関係", "周囲", "様子", "最後", "最初", "実際", "現実", "可能", "絶対", "必要", "十分",
    "普通", "特別", "簡単", "複雑", "重要", "基本", "詳細", "現在", "過去", "未来", "日常", "対照",
    "構造", "機能", "特徴", "定義", "分類", "性質", "役割", "要素", "一部", "最初", "最後", "左右",
    "上下", "前後", "内外", "中心", "周辺", "背景", "目的", "効果", "影響", "結果", "変化", "状態",
    "問題", "課題", "解決", "対応", "準備", "確認", "判断", "選択", "行動", "反応", "表現", "理解"
}

def extract_entities_from_sources(sources_dir):
    """
    Extracts important entities (character names, key terms with rubies, terms in brackets)
    from setting files to create a high-priority entity dictionary.
    """
    entities = set()
    if not os.path.exists(sources_dir):
        return entities

    # Add main characters from project config
    if writer_helper:
        main_chars = writer_helper.get_novel_setting("main_characters", ["アルフ", "ミーナ", "エイラ", "バスィム", "ザルコス", "ナディール", "レフ"])
    else:
        main_chars = ["アルフ", "ミーナ", "エイラ", "バスィム", "ザルコス", "ナディール", "レフ"]
    entities.update(main_chars)

    ruby_pattern = re.compile(r'([一-龠ぁ-んァ-ヴー]{2,15})（([ァ-ヴーa-zA-Z\s・]+)）')
    bracket_pattern = re.compile(r'『([^』]{2,15})』')
    char_pattern = re.compile(r'^([^\n\(\s【]{2,10})\s*\([a-zA-Z\s]+\)', re.MULTILINE)

    for filename in os.listdir(sources_dir):
        if not filename.endswith('.txt'):
            continue
        file_path = os.path.join(sources_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 1. Extract ruby bases and reading text
            for match in ruby_pattern.finditer(content):
                entities.add(match.group(1)) # Parent word (e.g. 大調律圏)
                entities.add(match.group(2)) # Ruby reading (e.g. ザ・グランド・テンプラメント)

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
            print(f"Warning: Failed to parse entity from {filename}: {e}", file=sys.stderr)

    # Filter out stopwords or empty strings
    entities = {e for e in entities if e and e not in STOPWORDS and len(e) >= 2}
    return entities

def extract_keywords_from_novel(text):
    """
    Extracts potential search keywords (Katakana and Kanji words) from the novel draft,
    excluding common stopwords.
    """
    katakana_pat = re.compile(r'[ァ-ヴー]{2,}')
    kanji_pat = re.compile(r'[一-龠]{2,}')
    
    keywords = set()
    keywords.update(katakana_pat.findall(text))
    keywords.update(kanji_pat.findall(text))
    
    # Filter out stopwords and short terms
    filtered = {
        kw for kw in keywords 
        if len(kw) >= 2 and kw not in STOPWORDS
    }
    return filtered

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
    sources_dir = os.path.join(root_dir, 'data', 'sources')
    
    if not os.path.exists(sources_dir):
        print(f"Error: Sources directory {sources_dir} not found. Please run sync_gdrive.py first.")
        sys.exit(1)

    # 1. Build Entity Dictionary from setting sources
    entity_words = extract_entities_from_sources(sources_dir)
    print(f"Extracted {len(entity_words)} high-priority entities from sources.")

    # 2. Read novel text and extract keywords
    with open(novel_path, 'r', encoding='utf-8') as f:
        novel_text = f.read()
    
    novel_keywords = extract_keywords_from_novel(novel_text)
    print(f"Extracted {len(novel_keywords)} valid keywords from novel.")
    
    # 3. Read and split source files into chunks
    source_files = [f for f in os.listdir(sources_dir) if f.endswith('.txt')]
    all_chunks = []
    
    # We will build document frequency (DF) to calculate IDF-like weights for keywords
    # DF maps: keyword -> number of chunks containing it
    df_counts = {}
    
    # Split source files into paragraph chunks
    raw_chunks_all = []
    for filename in source_files:
        file_path = os.path.join(sources_dir, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Split by double newlines to get paragraphs/sections
        raw_chunks = re.split(r'\n\s*\n', content)
        
        for i, raw_chunk in enumerate(raw_chunks):
            chunk_text = raw_chunk.strip()
            if not chunk_text:
                continue
            raw_chunks_all.append((filename, i, chunk_text))

    total_chunks = len(raw_chunks_all)
    
    # Pre-calculate DF for novel keywords in setting chunks
    for kw in novel_keywords:
        df = sum(1 for _, _, text in raw_chunks_all if kw in text)
        df_counts[kw] = df

    # 4. Calculate word weights and score each chunk
    # Word weight = base_weight * idf
    # Base weight: 10.0 for entities, 1.0 for other keywords
    # IDF = log(total_chunks / (df + 1)) + 1
    word_weights = {}
    for kw in novel_keywords:
        df = df_counts.get(kw, 0)
        idf = math.log(total_chunks / (df + 1)) + 1.0
        
        base_weight = 1.0
        if kw in entity_words:
            base_weight = 10.0  # High weight for main characters & setting keywords
            
        word_weights[kw] = base_weight * idf

    # Score chunks
    for filename, idx, chunk_text in raw_chunks_all:
        score = 0.0
        matched_kws = []
        for kw in novel_keywords:
            if kw in chunk_text:
                count = chunk_text.count(kw)
                score += count * word_weights[kw]
                matched_kws.append(kw)
                
        if score > 0:
            all_chunks.append({
                'file': filename,
                'index': idx,
                'text': chunk_text,
                'score': score,
                'matches': matched_kws
            })
                
    # 5. Sort chunks by score descending
    all_chunks.sort(key=lambda x: x['score'], reverse=True)
    
    # 6. Select top chunks up to a character limit (e.g., 20000 chars)
    selected_chunks = []
    current_length = 0
    MAX_CHARS = 20000
    
    output_content = "=== FILTERED SETTING CONTEXT ===\n"
    output_content += "This file contains automatically filtered relevant settings based on keywords in the chapter.\n\n"
    
    for chunk in all_chunks:
        chunk_header = f"--- Source: {chunk['file']} (Section {chunk['index']}, Score: {chunk['score']:.1f}) ---\n"
        # Optional: Print matched keywords for debug/transparency
        # chunk_header += f"Matches: {', '.join(chunk['matches'][:10])}\n"
        chunk_body = chunk['text'] + "\n\n"
        chunk_full = chunk_header + chunk_body
        
        if current_length + len(chunk_full) > MAX_CHARS:
            if not selected_chunks:
                output_content += chunk_header + chunk_body[:MAX_CHARS - len(chunk_header)] + "... (truncated)\n"
            break
            
        selected_chunks.append(chunk)
        output_content += chunk_full
        current_length += len(chunk_full)
        
    # Ensure directory of output path exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_content)
        
    print(f"Saved filtered context ({current_length} chars, {len(selected_chunks)} chunks) to {output_path}")

if __name__ == '__main__':
    main()
