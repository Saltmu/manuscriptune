import os
import re
import sys

def extract_keywords(text):
    # Extract Katakana words (2+ characters) and Kanji words (2+ characters)
    katakana_pat = re.compile(r'[ァ-ヴー]{2,}')
    kanji_pat = re.compile(r'[一-龠]{2,}')
    
    keywords = set()
    keywords.update(katakana_pat.findall(text))
    keywords.update(kanji_pat.findall(text))
    
    # Filter out keywords that are too short
    filtered = {kw for kw in keywords if len(kw) >= 2}
    return filtered

def score_chunk(chunk, keywords):
    score = 0
    # Simple count of keyword occurrences
    for kw in keywords:
        if kw in chunk:
            score += chunk.count(kw)
    return score

def main():
    if len(sys.argv) < 3:
        print("Usage: python filter_context.py [NOVEL_PATH] [OUTPUT_PATH]")
        sys.exit(1)
        
    novel_path = sys.argv[1]
    output_path = sys.argv[2]
    
    if not os.path.exists(novel_path):
        print(f"Error: Novel file {novel_path} not found.")
        sys.exit(1)
        
    # 1. Read novel text and extract keywords
    with open(novel_path, 'r', encoding='utf-8') as f:
        novel_text = f.read()
    
    keywords = extract_keywords(novel_text)
    print(f"Extracted {len(keywords)} potential keywords from novel.")
    
    # 2. Find source files
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources_dir = os.path.join(root_dir, 'data', 'sources')
    
    if not os.path.exists(sources_dir):
        print(f"Error: Sources directory {sources_dir} not found. Please run sync_gdrive.py first.")
        sys.exit(1)
        
    source_files = [f for f in os.listdir(sources_dir) if f.endswith('.txt')]
    
    all_chunks = []
    
    # 3. Read and split source files into chunks
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
            
            score = score_chunk(chunk_text, keywords)
            if score > 0:
                all_chunks.append({
                    'file': filename,
                    'index': i,
                    'text': chunk_text,
                    'score': score
                })
                
    # 4. Sort chunks by score descending
    all_chunks.sort(key=lambda x: x['score'], reverse=True)
    
    # 5. Select top chunks up to a character limit (e.g., 20000 chars)
    selected_chunks = []
    current_length = 0
    MAX_CHARS = 20000
    
    # Always include a header about what this file is
    output_content = "=== FILTERED SETTING CONTEXT ===\n"
    output_content += "This file contains automatically filtered relevant settings based on keywords in the chapter.\n\n"
    
    for chunk in all_chunks:
        chunk_header = f"--- Source: {chunk['file']} (Section {chunk['index']}, Score: {chunk['score']}) ---\n"
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
