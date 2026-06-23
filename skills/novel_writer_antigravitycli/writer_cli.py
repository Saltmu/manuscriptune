import os
import argparse
import subprocess
import json
import re

# 既存のヘルパーからプロット情報を取得するため、パスを追加してインポート
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'novel-writer')))
import writer_helper

def read_file(filepath):
    """ファイルを読み込むヘルパー関数"""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return ""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def get_episode_plot(plot_file, episode_title):
    """指定された話のプロット内容と、それが属する章のタイトルを取得する"""
    if not os.path.exists(plot_file):
        print(f"Error: Plot file not found: {plot_file}", file=sys.stderr)
        return None, ""
        
    plot_data = writer_helper.parse_plot(plot_file)
    
    # 全ての章から該当する話を探す
    for chapter_data in plot_data:
        chapter_title = chapter_data.get('title', '')
        for ep in chapter_data.get('episodes', []):
            if ep['title'] == episode_title or episode_title in ep['title'] or episode_title in ep['name']:
                return chapter_title, '\n'.join(ep['content'])
            
    print(f"Error: Episode '{episode_title}' not found in plot.", file=sys.stderr)
    return None, ""

def generate_prompt(chapter_title, episode_title, plot_content, novel_title=None, policy_global=None, policy_chapter=None, settings=None, character=None):
    """geminiに渡すプロンプト（指示文とコンテキストの結合）を生成する"""
    
    # 参照ファイルのパス（プロジェクトルートからの相対パスを想定）
    POLICY_FILE = policy_global if policy_global else writer_helper.resolve_novel_file_by_pattern("policy_global", "*執筆ポリシー_全体*.txt", "data/sources/00_1_執筆ポリシー_全体_ver.5.0.txt")
    POLICY_FILE_MACRO = policy_chapter if policy_chapter else writer_helper.resolve_novel_file_by_pattern("policy_chapter", "*執筆ポリシー_第*.txt", "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt")
    SETTING_FILE = settings if settings else writer_helper.resolve_novel_file_by_pattern("settings", "*設定資料集*.txt", "data/sources/09_0_重天の調律師_設定資料集.txt")
    CHARACTER_FILE = character if character else writer_helper.resolve_novel_file_by_pattern("character", "*キャラクター概要*.txt", "data/sources/03_1_第1幕キャラクター概要 ver.2.txt")
    
    policy_text = read_file(POLICY_FILE)
    policy_macro_text = read_file(POLICY_FILE_MACRO)
    setting_text = read_file(SETTING_FILE)
    character_text = read_file(CHARACTER_FILE)
    
    actual_title = novel_title if novel_title else writer_helper.get_novel_setting("title", "重天の調律師")
    prompt = f"""あなたは「{actual_title}」シリーズの専属作家です。
以下の「執筆ポリシー」「設定資料集」「キャラクター概要」を完全に把握し、ポリシーを厳守して物語を綴ってください。

==============================
【執筆ポリシー】
{policy_text}

{policy_macro_text}
==============================

==============================
【設定資料集】
{setting_text}
==============================

==============================
【キャラクター概要】
{character_text}
==============================

==============================
【今回執筆する対象のプロット】
対象: {chapter_title} {episode_title}

{plot_content}
==============================

【執筆指示】
上記のプロットに従い、「{chapter_title} {episode_title}」の本文を執筆してください。
・指示や注釈、挨拶などのメタなテキストは一切出力しないでください。小説の本文のみを出力してください。
・1話あたりの文字数に無理やり収めようとはせず、描写の密度を優先してください。
・執筆ポリシー（特に文体のリズム、特殊ルビ、地の文と会話のバランス、物理と叙情の描写）を必ず守ってください。

それでは、執筆を開始してください。
"""
    return prompt

def extract_numbers(text):
    """文字列から最初の数字を抽出する（例: '第1章' -> '1'）"""
    match = re.search(r'\d+', text)
    return match.group(0) if match else "0"

def main():
    parser = argparse.ArgumentParser(description="Use Antigravity CLI (agy) to write a novel episode.")
    parser.add_argument("--episode", required=True, help="Episode title (e.g., '第1話')")
    default_plot = writer_helper.resolve_novel_file_by_pattern("plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt")
    parser.add_argument("--plot-file", default=default_plot, help="Path to the plot file.")
    parser.add_argument("--model", default="Gemini 3.5 Flash (High)", help="Model to use with Antigravity CLI (default: Gemini 3.5 Flash (High))")
    parser.add_argument("--title", help="Novel title")
    parser.add_argument("--policy-global", help="Path to global policy file")
    parser.add_argument("--policy-chapter", help="Path to chapter policy file")
    parser.add_argument("--settings", help="Path to settings file")
    parser.add_argument("--character", help="Path to character overview file")
    
    args = parser.parse_args()
    
    # プロット内容の取得
    chapter_title, plot_content = get_episode_plot(args.plot_file, args.episode)
    if not plot_content:
        print("Failed to get plot content. Exiting.", file=sys.stderr)
        sys.exit(1)
        
    # プロンプトの生成
    prompt = generate_prompt(
        chapter_title,
        args.episode,
        plot_content,
        novel_title=args.title,
        policy_global=args.policy_global,
        policy_chapter=args.policy_chapter,
        settings=args.settings,
        character=args.character
    )
    
    # 出力ファイル名の決定 (novels/X_Y.txt)
    ch_num = extract_numbers(chapter_title) if chapter_title else "0"
    ep_num = extract_numbers(args.episode)
    output_filename = f"novels/{ch_num}_{ep_num}.txt"
    
    # ensure output directory exists
    os.makedirs("novels", exist_ok=True)
    
    print(f"Starting writing process for {chapter_title} {args.episode}...")
    print(f"Model: {args.model}")
    print(f"Output will be saved to: {output_filename}")
    
    # Antigravity CLI の呼び出し
    # echo プロンプト | agy -p "" --model model で実行する
    # -p で空の文字列を渡し、標準入力から本文を流し込む
    cmd = ["agy", "-p", "", "--model", args.model]
    
    try:
        # subprocess.run を使って、標準入力を経由してプロンプトを渡す
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(input=prompt)
        
        if process.returncode != 0:
            print(f"Error calling Antigravity CLI (agy):", file=sys.stderr)
            print(stderr, file=sys.stderr)
            sys.exit(process.returncode)
            
        # 結果をファイルに保存
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(stdout.strip() + "\n")
            
        print(f"Success! Novel saved to {output_filename}")
        
    except FileNotFoundError:
        print("Error: 'agy' CLI not found. Please ensure it is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
