import argparse
import os
import re
import subprocess

# 既存のヘルパーからプロット情報を取得するため、パスを追加してインポート
import sys
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'novel-writer')))
import writer_helper


def read_file(filepath):
    """ファイルを読み込むヘルパー関数"""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return ""
    with open(filepath, encoding='utf-8') as f:
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

def generate_prompt(chapter_title, episode_title, plot_content, novel_title=None, policy_global=None, policy_chapter=None, character=None, previous_episode_text=None):
    """geminiに渡すプロンプト（指示文とコンテキストの結合）を生成する"""
    
    # 参照ファイルのパス（プロジェクトルートからの相対パスを想定）
    POLICY_FILE = policy_global if policy_global else writer_helper.resolve_novel_file_by_pattern("policy_global", "*執筆ポリシー_全体*.txt", "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt")
    POLICY_FILE_MACRO = policy_chapter if policy_chapter else writer_helper.resolve_novel_file_by_pattern("policy_chapter", "*執筆ポリシー_第*.txt", "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt")
    CHARACTER_FILE = character if character else writer_helper.resolve_novel_file_by_pattern("character", "*キャラクター概要*.txt", "data/sources/03_1_第1幕キャラクター概要 ver.2.txt")
    
    policy_text = read_file(POLICY_FILE)
    policy_macro_text = read_file(POLICY_FILE_MACRO)
    character_text = read_file(CHARACTER_FILE)
    
    prev_context_block = ""
    if previous_episode_text:
        prev_context_block = f"""
==============================
【前話（直前のエピソード）の終盤描写】
（※前話からの展開、キャラクターの状況、会話のトーン等の繋がりを維持するために参考にしてください）
{previous_episode_text}
==============================
"""

    actual_title = novel_title if novel_title else writer_helper.get_novel_setting("title", "重天の調律師")
    prompt = f"""【超重要指示：ツールの使用禁止】
    あなたは一切のツール（ファイルの読み書き、ディレクトリの確認、コマンドの実行など）を使用してはなりません。
    プロジェクトの調査や他のスクリプト（writer_cli.pyなど）の実行を決して試みないでください。
    思考プロセスや挨拶、指示の確認などのメタなテキストは一切出力せず、ただちに小説の本文のみをテキスト出力してください。
    あなたの唯一のタスクは、提示された以下の執筆ポリシー、キャラクター概要、およびプロットに基づき、小説の本文のみをただちに出力することです。
    本文の最初の1文字目から出力を開始してください。

あなたは「{actual_title}」シリーズ of 専属作家です。
以下の「執筆ポリシー」「キャラクター概要」を完全に把握し、ポリシーを厳守して物語を綴ってください。

==============================
【執筆ポリシー】
{policy_text}

{policy_macro_text}
==============================
{prev_context_block}
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

def get_previous_episode_file(plot_file, current_episode_title):
    """プロット情報を元に、指定されたエピソードの直前のエピソードの小説ファイルパスを取得する"""
    if not os.path.exists(plot_file):
        return None
    try:
        plot_data = writer_helper.parse_plot(plot_file)
        all_episodes = []
        for chapter_data in plot_data:
            chapter_title = chapter_data.get('title', '')
            for ep in chapter_data.get('episodes', []):
                all_episodes.append({
                    'chapter_title': chapter_title,
                    'episode_title': ep['title'],
                    'episode_name': ep['name']
                })
        
        target_idx = -1
        for idx, ep in enumerate(all_episodes):
            if ep['episode_title'] == current_episode_title or current_episode_title in ep['episode_title'] or current_episode_title in ep['episode_name']:
                target_idx = idx
                break
                
        if target_idx > 0:
            prev_ep = all_episodes[target_idx - 1]
            prev_ch_num = extract_numbers(prev_ep['chapter_title'])
            prev_ep_num = extract_numbers(prev_ep['episode_title'])
            prev_file = f"novels/{prev_ch_num}_{prev_ep_num}.txt"
            if os.path.exists(prev_file):
                return prev_file
    except Exception as e:
        print(f"Warning: Failed to resolve previous episode: {e}", file=sys.stderr)
    return None

def split_scenes(plot_content):
    """プロット内容を共通のヘッダー情報と、各シーンのプロットに分割する"""
    lines = plot_content.split('\n')
    scenes = []
    current_scene_title = None
    current_scene_lines = []
    
    scene_pattern = re.compile(r'^(シーン\s*[0-9一二三四五六七八九十]+：.*)$')
    common_header = []
    has_started_scenes = False
    
    for line in lines:
        match = scene_pattern.match(line.strip())
        if match:
            has_started_scenes = True
            if current_scene_title:
                scenes.append((current_scene_title, '\n'.join(current_scene_lines).strip()))
            current_scene_title = match.group(1)
            current_scene_lines = []
        else:
            if not has_started_scenes:
                common_header.append(line)
            else:
                current_scene_lines.append(line)
                
    if current_scene_title:
        scenes.append((current_scene_title, '\n'.join(current_scene_lines).strip()))
        
    return '\n'.join(common_header).strip(), scenes

def run_self_check(novel_content, policy_text, policy_macro_text, plot_content, model):
    """LLMを用いて執筆された本文のポリシー自己チェックと自動リライトを行う"""
    print("Starting self-verification for policy compliance...")
    
    check_prompt = f"""あなたは小説の厳しい校閲編集者です。
提示された小説本文が、「執筆ポリシー」および「演出指示・禁止事項」を満たしているか厳密にチェックしてください。

==============================
【執筆ポリシー】
{policy_text}

{policy_macro_text}
==============================

==============================
【プロットと演出指示・禁止事項】
{plot_content}
==============================

==============================
【小説本文】
{novel_content}
==============================

【指示】
上記の小説本文をポリシーおよび禁止事項と照らし合わせ、違反している箇所を検出してください。
出力は必ず ```yaml で始まるYAMLコードブロックのみにしてください。
メタな解説や挨拶は一切含めないでください。

指摘事項がある場合は、以下のように出力してください：
```yaml
violations:
  - original: "（違反のある原文の抜粋）"
    reason: "（違反の理由。例：禁止語『ネフェス』が使用されています）"
    suggestion: "（どのように修正すべきかの具体的な提案。例：『重力制御』または『調律』と書き換えてください）"
```

もし違反が一切ない場合は、空のリストを出力してください：
```yaml
violations: []
```
"""
    
    # agyの呼び出し
    cmd = ["agy", "-p", "", "--model", model]
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        stdout, stderr = process.communicate(input=check_prompt)
        if process.returncode != 0:
            print(f"Warning: Self-check execution failed: {stderr}", file=sys.stderr)
            return novel_content
            
        result_text = stdout.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result_text)
        yaml_content = yaml_match.group(1).strip() if yaml_match else result_text
        
        # PyYAMLを利用して違反内容を解析
        import yaml
        data = yaml.safe_load(yaml_content)
        violations = data.get("violations", []) if isinstance(data, dict) else []
        
        if not violations:
            print("[Self-Check] No violations found. Compliance OK.")
            return novel_content
            
        print(f"[Self-Check] Found {len(violations)} violations. Starting rewrite...")
        
        # 違反がある場合、リライトを実行
        rewrite_prompt = f"""あなたは小説の優秀な編集者です。
以下の【小説本文】について、検出された【指摘事項】をすべて解消するように適切に書き換えてください。

==============================
【検出された指摘事項】
{yaml_content}
==============================

==============================
【小説本文】
{novel_content}
==============================

【出力ルール】
・修正・書き換え後の小説本文全体のみを出力してください。
・解説、挨拶、マークダウン of コードブロック（```）などは一切出力しないでください。
・指摘された問題点（語彙、設定矛盾、表現など）のみを解消し、文体やニュアンスはそのまま維持してください。
"""
        
        # リライト実行
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        stdout, stderr = process.communicate(input=rewrite_prompt)
        if process.returncode == 0:
            rewritten_text = stdout.strip()
            rewritten_text = re.sub(r"^```[a-zA-Z]*\n", "", rewritten_text)
            rewritten_text = re.sub(r"\n```$", "", rewritten_text).strip()
            print("[Self-Check] Rewrite completed successfully.")
            return rewritten_text
        else:
            print(f"Warning: Rewrite failed: {stderr}", file=sys.stderr)
            
    except Exception as e:
        print(f"Warning: Error during self-check or rewrite: {e}", file=sys.stderr)
        
    return novel_content

def extract_numbers(text):
    """文字列から最初の数字を抽出する（例: '第1章' -> '1'）"""
    match = re.search(r'\d+', text)
    return match.group(0) if match else "0"

def generate_all_at_once(prompt, model):
    """従来の1回の呼び出しで全本文を生成するロジック"""
    cmd = ["agy", "-p", "", "--model", model]
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    
    # stdinへの書き込みを別スレッドで行い、デッドロックを防ぐ
    def write_stdin():
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except Exception as e:
            print(f"Error writing to stdin: {e}", file=sys.stderr)

    stdin_thread = threading.Thread(target=write_stdin)
    stdin_thread.start()

    full_output = []
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            sys.stdout.write(line)
            sys.stdout.flush()
            full_output.append(line)

    stdin_thread.join()
    stderr = process.stderr.read()
    
    if process.returncode != 0:
        print("Error calling Antigravity CLI (agy):", file=sys.stderr)
        print(stderr, file=sys.stderr)
        sys.exit(process.returncode)
        
    return "".join(full_output)

def main():
    parser = argparse.ArgumentParser(description="Use Antigravity CLI (agy) to write a novel episode.")
    parser.add_argument("--episode", required=True, help="Episode title (e.g., '第1話')")
    default_plot = writer_helper.resolve_novel_file_by_pattern("plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt")
    parser.add_argument("--plot-file", default=default_plot, help="Path to the plot file.")
    parser.add_argument("--model", default="Gemini 3.5 Flash (High)", help="Model to use with Antigravity CLI (default: Gemini 3.5 Flash (High))")
    parser.add_argument("--title", help="Novel title")
    parser.add_argument("--policy-global", help="Path to global policy file")
    parser.add_argument("--policy-chapter", help="Path to chapter policy file")
    parser.add_argument("--character", help="Path to character overview file")
    parser.add_argument("--step-by-step", action="store_true", help="Write the episode scene by scene.")
    parser.add_argument("--self-check", action="store_true", help="Perform self-verification and rewrite if needed.")
    
    args = parser.parse_args()
    
    # プロット内容の取得
    chapter_title, plot_content = get_episode_plot(args.plot_file, args.episode)
    if not plot_content:
        print("Failed to get plot content. Exiting.", file=sys.stderr)
        sys.exit(1)
        
    # 前話の文脈をロード（コンテキストリレー）
    prev_file = get_previous_episode_file(args.plot_file, args.episode)
    prev_text = None
    if prev_file:
        print(f"Loading context from previous episode: {prev_file}")
        full_prev = read_file(prev_file)
        if len(full_prev) > 1500:
            prev_text = "...\n" + full_prev[-1500:]
        else:
            prev_text = full_prev

    # 出力ファイル名の決定 (novels/X_Y.txt)
    ch_num = extract_numbers(chapter_title) if chapter_title else "0"
    ep_num = extract_numbers(args.episode)
    output_filename = f"novels/{ch_num}_{ep_num}.txt"
    
    # ensure output directory exists
    os.makedirs("novels", exist_ok=True)
    
    print(f"Starting writing process for {chapter_title} {args.episode}...")
    print(f"Model: {args.model}")
    if args.step_by_step:
        print("Mode: Step-by-Step (Scene-based)")
    if args.self_check:
        print("Verification: Policy Self-Check enabled")
    print(f"Output will be saved to: {output_filename}")
    
    novel_content = ""
    
    try:
        if args.step_by_step:
            # プロットをシーンに分割
            common_header, scenes = split_scenes(plot_content)
            
            # ポリシーファイルのパスを解決
            POLICY_FILE = args.policy_global if args.policy_global else writer_helper.resolve_novel_file_by_pattern("policy_global", "*執筆ポリシー_全体*.txt", "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt")
            POLICY_FILE_MACRO = args.policy_chapter if args.policy_chapter else writer_helper.resolve_novel_file_by_pattern("policy_chapter", "*執筆ポリシー_第*.txt", "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt")
            CHARACTER_FILE = args.character if args.character else writer_helper.resolve_novel_file_by_pattern("character", "*キャラクター概要*.txt", "data/sources/03_1_第1幕キャラクター概要 ver.2.txt")
            
            prev_context_block = ""
            if prev_text:
                prev_context_block = f"""
==============================
【前話（直前のエピソード）の終盤描写】
（※前話からの展開、キャラクターの状況、会話のトーン等の繋がりを維持するために参考にしてください）
{prev_text}
==============================
"""

            if not scenes:
                print("No scenes detected in plot. Falling back to single-pass writing.", file=sys.stderr)
                prompt = generate_prompt(
                    chapter_title,
                    args.episode,
                    plot_content,
                    novel_title=args.title,
                    policy_global=args.policy_global,
                    policy_chapter=args.policy_chapter,
                    character=args.character,
                    previous_episode_text=prev_text
                )
                novel_content = generate_all_at_once(prompt, args.model)
            else:
                print(f"Detected {len(scenes)} scenes. Starting step-by-step writing...")
                context_written = ""
                
                # スレッド管理用にインポート（元コードで threading をインポート済み）
                import threading
                
                for s_idx, (s_title, s_plot) in enumerate(scenes, 1):
                    print(f"\n--- Writing Scene {s_idx}/{len(scenes)}: {s_title} ---")
                    
                    scene_written_context = ""
                    if context_written:
                        scene_written_context = f"""
==============================
【既に執筆済みの本文（シーンの流れ）】
{context_written}
==============================
"""
                    
                    scene_prompt = f"""【超重要指示：ツールの使用禁止】
あなたは一切のツールを使用してはなりません。
思考プロセスやメタな解説などは一切出力せず、ただちに指定されたシーンの本文のみを出力してください。

あなたは「{args.title or "重天の調律師"}」の専属作家です。
以下の「執筆ポリシー」を厳守し、「既に執筆済みの本文」の展開、口調、描写リズムを自然に引き継いだ形で、「今回執筆する対象のシーンプロット」の本文を執筆してください。

==============================
【執筆ポリシー】
{read_file(POLICY_FILE)}
{read_file(POLICY_FILE_MACRO)}
==============================
{prev_context_block}
==============================
【キャラクター概要】
{read_file(CHARACTER_FILE)}
==============================
{scene_written_context}
==============================
【今回執筆する対象のシーンプロット】
対象: {chapter_title} {args.episode}
現在のシーン: {s_title}

{s_plot}
==============================

【執筆指示】
「既に執筆済みの本文」の直後からシームレスに繋がるように、今回のシーン「{s_title}」の本文のみを出力してください。
・挨拶や解説、マークダウンのコードブロック等は一切不要です。小説の本文のみを出力してください。
・前の文脈を繰り返さないでください。今回指定されたプロット部分のみを新しく書き足してください。
"""
                    
                    # シーンを生成
                    cmd = ["agy", "-p", "", "--model", args.model]
                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding='utf-8'
                    )
                    
                    def write_scene_stdin(proc=process, prompt=scene_prompt):
                        try:
                            proc.stdin.write(prompt)
                            proc.stdin.close()
                        except Exception as e:
                            print(f"Error writing scene stdin: {e}", file=sys.stderr)
                            
                    stdin_thread = threading.Thread(target=write_scene_stdin)
                    stdin_thread.start()
                    
                    scene_output = []
                    while True:
                        line = process.stdout.readline()
                        if not line and process.poll() is not None:
                            break
                        if line:
                            sys.stdout.write(line)
                            sys.stdout.flush()
                            scene_output.append(line)
                            
                    stdin_thread.join()
                    
                    if process.returncode != 0:
                        stderr_msg = process.stderr.read()
                        print(f"Error generating scene {s_idx}: {stderr_msg}", file=sys.stderr)
                        sys.exit(process.returncode)
                        
                    scene_content = "".join(scene_output).strip()
                    scene_content = re.sub(r"^```[a-zA-Z]*\n", "", scene_content)
                    scene_content = re.sub(r"\n```$", "", scene_content).strip()
                    
                    print(f"\n[Generated Scene {s_idx} length: {len(scene_content)} chars]")
                    
                    if context_written:
                        context_written += "\n\n" + scene_content
                    else:
                        context_written = scene_content
                        
                novel_content = context_written
        else:
            # 一括生成
            prompt = generate_prompt(
                chapter_title,
                args.episode,
                plot_content,
                novel_title=args.title,
                policy_global=args.policy_global,
                policy_chapter=args.policy_chapter,
                character=args.character,
                previous_episode_text=prev_text
            )
            novel_content = generate_all_at_once(prompt, args.model)
            
        # ポリシーの自己検知チェック & リライト
        if args.self_check and novel_content:
            POLICY_FILE = args.policy_global if args.policy_global else writer_helper.resolve_novel_file_by_pattern("policy_global", "*執筆ポリシー_全体*.txt", "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt")
            POLICY_FILE_MACRO = args.policy_chapter if args.policy_chapter else writer_helper.resolve_novel_file_by_pattern("policy_chapter", "*執筆ポリシー_第*.txt", "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt")
            policy_text = read_file(POLICY_FILE)
            policy_macro_text = read_file(POLICY_FILE_MACRO)
            
            novel_content = run_self_check(
                novel_content,
                policy_text,
                policy_macro_text,
                plot_content,
                args.model
            )
            
        # 結果をファイルに保存
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(novel_content.strip() + "\n")
            
        print(f"\nSuccess! Novel saved to {output_filename}")
        
    except FileNotFoundError:
        print("Error: 'agy' CLI not found. Please ensure it is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
