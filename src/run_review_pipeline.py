import os
import re
import sys
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add skills/novel-writer to path to use writer_helper
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'skills', 'novel-writer')))
import writer_helper

def read_file(filepath):
    if not filepath or not os.path.exists(filepath):
        return ""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def run_formatter(input_file, output_file):
    """
    Runs the novel mechanical formatter on the input file.
    """
    formatter_script = os.path.join("skills", "novel-formatter", "scripts", "novel_formatter_helper.py")
    if not os.path.exists(formatter_script):
        print(f"Warning: Formatter script '{formatter_script}' not found. Performing fallback copy.")
        content = read_file(input_file)
        content = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', content)
        content = re.sub(r'\(\d+(?:,\s*\d+)*\)', '', content)
        content = re.sub(r'【\d+(?:,\s*\d+)*】', '', content)
        content = re.sub(r'([。、！？])[\t 　]+', r'\1', content)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return
        
    cmd = ["poetry", "run", "python", formatter_script, input_file, "-o", output_file]
    print(f"Running mechanical formatter: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def run_filter_context(formatted_file, output_file):
    """
    Runs the filter_context script to extract relevant settings.
    """
    filter_script = os.path.join("src", "filter_context.py")
    if not os.path.exists(filter_script):
        print(f"Warning: filter_context.py not found. Skipping context filtering.")
        return False
        
    cmd = ["poetry", "run", "python", filter_script, formatted_file, output_file]
    print(f"Running context filter: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return True
    else:
        print(f"Warning: Context filter failed with error:\n{res.stderr}", file=sys.stderr)
        return False

def get_skill_prompt(skill_name, target_text, output_dir):
    """
    Generates the review prompt for a specific skill, attaching relevant source files or filtered context.
    """
    skill_md_path = os.path.join("skills", skill_name, "SKILL.md")
    if not os.path.exists(skill_md_path):
        print(f"Error: SKILL.md not found for skill '{skill_name}' at {skill_md_path}", file=sys.stderr)
        return None
        
    skill_instruction = read_file(skill_md_path)
    
    context_text = ""
    def get_latest_file(pattern):
        return writer_helper.resolve_latest_file(os.path.join("data", "sources", pattern), None)

    if skill_name == 'logic-consistency-reviewer':
        filtered_context_path = os.path.join(output_dir, "01_filtered_context.txt")
        if os.path.exists(filtered_context_path):
            print(f"[{skill_name}] Loading filtered context from 01_filtered_context.txt")
            context_text += f"\n【フィルタリング済み設定資料】\n{read_file(filtered_context_path)}\n"
        else:
            # Fallback to raw files
            print(f"[{skill_name}] Warning: filtered context not found. Loading raw sources.")
            setting_file = get_latest_file("*設定資料集*.txt")
            char_file = get_latest_file("*キャラクター概要*.txt")
            plot_file = get_latest_file("*プロット*.txt")
            if setting_file:
                context_text += f"\n【設定資料集】\n{read_file(setting_file)}\n"
            if char_file:
                context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
            if plot_file:
                context_text += f"\n【プロット】\n{read_file(plot_file)}\n"
            
    elif skill_name == 'style-expression-reviewer':
        char_file = get_latest_file("*キャラクター概要*.txt")
        policy_file = get_latest_file("*執筆ポリシー_全体*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if policy_file:
            context_text += f"\n【執筆ポリシー】\n{read_file(policy_file)}\n"
            
    prompt = f"""{skill_instruction}

==============================
{context_text}
==============================

==============================
【校閲対象の小説テキスト】
{target_text}
==============================

【実行指示】
上記の小説テキストに対し、あなたの役割に従って校閲を行ってください。
指摘事項がある場合は、指定されたYAML形式で出力してください。
・出力は必ず ```yaml で始まるYAMLコードブロックのみにしてください。
・挨拶や解説などのメタなテキストは一切出力しないでください。
・もし指摘事項がない場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```
"""
    return prompt

def run_single_review_skill(skill_name, target_text, output_file, model, output_dir):
    """
    Executes a single review skill via agy CLI.
    """
    print(f"[{skill_name}] Preparing review prompt...")
    prompt = get_skill_prompt(skill_name, target_text, output_dir)
    if not prompt:
        return skill_name, False, "Failed to generate prompt"
        
    print(f"[{skill_name}] Running agy CLI ({model})...")
    cmd = ["agy", "-p", "", "--model", model]
    
    try:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(input=prompt)
        
        if process.returncode != 0:
            return skill_name, False, f"agy error: {stderr}"
            
        result_text = stdout.strip()
        yaml_match = re.search(r'```yaml\s*([\s\S]*?)```', result_text)
        if yaml_match:
            yaml_content = yaml_match.group(1).strip()
        else:
            yaml_content = result_text
            
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content + "\n")
            
        return skill_name, True, f"Saved to {output_file}"
        
    except FileNotFoundError:
        return skill_name, False, "'agy' CLI not found"
    except Exception as e:
        return skill_name, False, f"Unexpected error: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description="Run the entire parallel review pipeline for a novel draft.")
    parser.add_argument("target_file", help="Path to the novel txt file to review.")
    parser.add_argument("--model", default="Gemini 3.5 Flash (High)", help="AI Model to use for review skills.")
    parser.add_argument("--dir", help="Output directory path (defaults to novel_check_results/[basename])")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel worker threads.")
    parser.add_argument("--no-server", action="store_true", help="Skip launching the web server editor at the end.")
    args = parser.parse_args()
    
    if not os.path.exists(args.target_file):
        print(f"Error: Target file '{args.target_file}' not found.", file=sys.stderr)
        sys.exit(1)
        
    target_path = Path(args.target_file)
    basename = target_path.stem
    output_dir = args.dir if args.dir else os.path.join("novel_check_results", basename)
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"=== Review Pipeline Starting ===")
    print(f"Target: {target_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Model: {args.model}\n")
    
    # Step 1: Run Formatter
    formatted_draft = os.path.join(output_dir, "01_formatted.txt")
    try:
        run_formatter(str(target_path), formatted_draft)
        print(f"[OK] Format completed: {formatted_draft}\n")
    except Exception as e:
        print(f"[ERROR] Formatting failed: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Step 2: Run Context Filter
    filtered_context = os.path.join(output_dir, "01_filtered_context.txt")
    run_filter_context(formatted_draft, filtered_context)
        
    # Read formatted draft text
    target_text = read_file(formatted_draft)
    
    # Step 3: Define review tasks (Logic and Style integrated reviewers)
    review_skills = {
        'logic-consistency-reviewer': "02_logic_consistency.yaml",
        'style-expression-reviewer': "03_style_expression.yaml"
    }
    
    results = []
    
    # Execute in parallel
    print(f"Spawning {len(review_skills)} review skills in parallel...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for skill, yaml_name in review_skills.items():
            output_yaml = os.path.join(output_dir, yaml_name)
            futures[executor.submit(run_single_review_skill, skill, target_text, output_yaml, args.model, output_dir)] = skill
            
        for future in as_completed(futures):
            skill = futures[future]
            try:
                skill_name, success, msg = future.result()
                results.append((skill_name, success, msg))
                if success:
                    print(f"[OK] {skill_name}: {msg}")
                else:
                    print(f"[FAIL] {skill_name}: {msg}", file=sys.stderr)
            except Exception as exc:
                print(f"[FAIL] {skill} generated an exception: {exc}", file=sys.stderr)
                results.append((skill, False, str(exc)))
                
    # Step 4: Run integration report
    print("\nIntegrating review results...")
    integration_script = os.path.join("src", "integrate_findings.py")
    if os.path.exists(integration_script):
        cmd = ["poetry", "run", "python", integration_script, "--dir", output_dir, "--model", args.model]
        print(f"Running: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print("[OK] Reports integrated successfully.")
            print(f"Consolidated Report: {os.path.join(output_dir, '00_integrated_report.md')}")
            print(f"Consolidated YAML  : {os.path.join(output_dir, '00_integrated_findings.yaml')}")
        else:
            print(f"[ERROR] Failed to run integrate_findings.py: {res.stderr}", file=sys.stderr)
    else:
        print("[WARNING] integrate_findings.py not found. Integration skipped.", file=sys.stderr)
        
    # Step 5: Start Review Editor Server
    if not args.no_server:
        print("\nStarting Interactive Review Editor UI...")
        server_script = os.path.join("src", "review_server.py")
        if os.path.exists(server_script):
            cmd = ["poetry", "run", "python", server_script, formatted_draft, os.path.join(output_dir, "00_integrated_findings.yaml")]
            print(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd)
        else:
            print("[WARNING] review_server.py not found. Interactive UI skipped.", file=sys.stderr)
            
    print("\n=== Review Pipeline Finished ===")

if __name__ == '__main__':
    main()
