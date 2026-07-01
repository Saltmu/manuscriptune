import argparse
import os
import re
import sys

# 既存のヘルパーからプロット情報を取得するため、パスを追加してインポート
from src.utils import plot_parser, project_config
from src.utils.ai_client import AgyClientError
from src.utils.ai_task import (
    NovelPolicyCheckInput,
    NovelPolicyCheckTask,
    NovelRewriteInput,
    NovelRewriteTask,
    NovelSceneWritingInput,
    NovelSceneWritingTask,
    NovelWritingInput,
    NovelWritingTask,
)


class WriterHelperMock:
    parse_plot = staticmethod(plot_parser.parse_plot)
    resolve_novel_file_by_pattern = staticmethod(
        project_config.resolve_novel_file_by_pattern
    )
    get_novel_setting = staticmethod(project_config.get_novel_setting)


writer_helper = WriterHelperMock


def read_file(filepath):
    """ファイルを読み込むヘルパー関数"""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return ""
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def get_episode_plot(plot_file, episode_title):
    """指定された話のプロット内容と、それが属する章のタイトルを取得する"""
    if not os.path.exists(plot_file):
        print(f"Error: Plot file not found: {plot_file}", file=sys.stderr)
        return None, ""

    plot_data = writer_helper.parse_plot(plot_file)

    # 全ての章から該当する話を探す
    for chapter_data in plot_data:
        chapter_title = chapter_data.get("title", "")
        for ep in chapter_data.get("episodes", []):
            if (
                ep["title"] == episode_title
                or episode_title in ep["title"]
                or episode_title in ep["name"]
            ):
                return chapter_title, "\n".join(ep["content"])

    print(f"Error: Episode '{episode_title}' not found in plot.", file=sys.stderr)
    return None, ""


def get_previous_episode_file(plot_file, current_episode_title):
    """プロット情報を元に、指定されたエピソードの直前のエピソードの小説ファイルパスを取得する"""
    if not os.path.exists(plot_file):
        return None
    try:
        plot_data = writer_helper.parse_plot(plot_file)
        all_episodes = []
        for chapter_data in plot_data:
            chapter_title = chapter_data.get("title", "")
            for ep in chapter_data.get("episodes", []):
                all_episodes.append(
                    {
                        "chapter_title": chapter_title,
                        "episode_title": ep["title"],
                        "episode_name": ep["name"],
                    }
                )

        target_idx = -1
        for idx, ep in enumerate(all_episodes):
            if (
                ep["episode_title"] == current_episode_title
                or current_episode_title in ep["episode_title"]
                or current_episode_title in ep["episode_name"]
            ):
                target_idx = idx
                break

        if target_idx > 0:
            prev_ep = all_episodes[target_idx - 1]
            prev_ch_num = extract_numbers(prev_ep["chapter_title"])
            prev_ep_num = extract_numbers(prev_ep["episode_title"])
            prev_file = f"novels/{prev_ch_num}_{prev_ep_num}.txt"
            if os.path.exists(prev_file):
                return prev_file
    except Exception as e:
        print(f"Warning: Failed to resolve previous episode: {e}", file=sys.stderr)
    return None


def get_neighboring_episodes_plots(plot_file, current_episode_title):
    """
    指定されたエピソードの「前話」と「後話」のプロット情報を取得する。
    """
    if not os.path.exists(plot_file):
        return None, None

    try:
        plot_data = writer_helper.parse_plot(plot_file)
        all_episodes = []
        for chapter_data in plot_data:
            chapter_title = chapter_data.get("title", "")
            for ep in chapter_data.get("episodes", []):
                all_episodes.append(
                    {
                        "chapter_title": chapter_title,
                        "episode_title": ep["title"],
                        "episode_name": ep["name"],
                        "content": ep["content"],
                    }
                )

        target_idx = -1
        for idx, ep in enumerate(all_episodes):
            if (
                ep["episode_title"] == current_episode_title
                or current_episode_title in ep["episode_title"]
                or current_episode_title in ep["episode_name"]
            ):
                target_idx = idx
                break

        if target_idx == -1:
            return None, None

        prev_plot = None
        next_plot = None

        if target_idx > 0:
            prev_ep = all_episodes[target_idx - 1]
            prev_plot = {
                "title": f"{prev_ep['chapter_title']} {prev_ep['episode_title']}（{prev_ep['episode_name']}）",
                "content": "\n".join(prev_ep["content"]),
            }

        if target_idx < len(all_episodes) - 1:
            next_ep = all_episodes[target_idx + 1]
            next_plot = {
                "title": f"{next_ep['chapter_title']} {next_ep['episode_title']}（{next_ep['episode_name']}）",
                "content": "\n".join(next_ep["content"]),
            }

        return prev_plot, next_plot
    except Exception as e:
        print(f"Warning: Failed to resolve neighboring episodes: {e}", file=sys.stderr)
        return None, None


def build_neighbor_plots_block(prev_plot, next_plot):
    if not prev_plot and not next_plot:
        return ""

    block = "【関連エピソードのプロット（参考情報）】\n※前後の展開の整合性を保つための参考情報です。今回の執筆対象ではありません。\n"
    if prev_plot:
        block += f"\n◆ 前話のプロット：{prev_plot['title']}\n{prev_plot['content']}\n"
    if next_plot:
        block += f"\n◆ 後話のプロット：{next_plot['title']}\n{next_plot['content']}\n"
    return block


def split_scenes(plot_content):
    """プロット内容を共通のヘッダー情報と、各シーンのプロットに分割する"""
    lines = plot_content.split("\n")
    scenes = []
    current_scene_title = None
    current_scene_lines = []

    scene_pattern = re.compile(r"^(シーン\s*[0-9一二三四五六七八九十]+：.*)$")
    common_header = []
    has_started_scenes = False

    for line in lines:
        match = scene_pattern.match(line.strip())
        if match:
            has_started_scenes = True
            if current_scene_title:
                scenes.append(
                    (current_scene_title, "\n".join(current_scene_lines).strip())
                )
            current_scene_title = match.group(1)
            current_scene_lines = []
        elif not has_started_scenes:
            common_header.append(line)
        else:
            current_scene_lines.append(line)

    if current_scene_title:
        scenes.append((current_scene_title, "\n".join(current_scene_lines).strip()))

    return "\n".join(common_header).strip(), scenes


def run_self_check(novel_content, policy_text, policy_macro_text, plot_content, model):
    """LLMを用いて執筆された本文のポリシー自己チェックと自動リライトを行う"""
    print("Starting self-verification for policy compliance...")

    try:
        check_task = NovelPolicyCheckTask(model=model)
        check_input = NovelPolicyCheckInput(
            novel_content=novel_content,
            policy_text=policy_text,
            policy_macro_text=policy_macro_text,
            plot_content=plot_content,
        )
        yaml_content = check_task.execute(check_input)

        # PyYAMLを利用して違反内容を解析
        import yaml

        data = yaml.safe_load(yaml_content)
        violations = data.get("violations", []) if isinstance(data, dict) else []

        if not violations:
            print("[Self-Check] No violations found. Compliance OK.")
            return novel_content

        print(f"[Self-Check] Found {len(violations)} violations. Starting rewrite...")

        # 違反がある場合、リライトを実行
        rewrite_task = NovelRewriteTask(model=model)
        rewrite_input = NovelRewriteInput(
            novel_content=novel_content,
            yaml_content=yaml_content,
        )
        rewritten_text = rewrite_task.execute(rewrite_input)
        print("[Self-Check] Rewrite completed successfully.")
        return rewritten_text

    except Exception as e:
        print(f"Warning: Error during self-check or rewrite: {e}", file=sys.stderr)

    return novel_content


def extract_numbers(text):
    """文字列から最初の数字を抽出する（例: '第1章' -> '1'）"""
    match = re.search(r"\d+", text)
    return match.group(0) if match else "0"


def _resolve_policy_paths(args) -> tuple[str, str, str]:
    """
    Resolves paths for policy and character overview files.
    """
    policy_global = (
        args.policy_global
        if args.policy_global
        else writer_helper.resolve_novel_file_by_pattern(
            "policy_global",
            "*執筆ポリシー_全体*.txt",
            "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt",
        )
    )
    policy_chapter = (
        args.policy_chapter
        if args.policy_chapter
        else writer_helper.resolve_novel_file_by_pattern(
            "policy_chapter",
            "*執筆ポリシー_第*.txt",
            "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt",
        )
    )
    character = (
        args.character
        if args.character
        else writer_helper.resolve_novel_file_by_pattern(
            "character",
            "*キャラクター概要*.txt",
            "data/sources/03_1_第1幕キャラクター概要 ver.2.txt",
        )
    )
    return policy_global, policy_chapter, character


def generate_prompt(
    chapter_title,
    episode_title,
    plot_content,
    novel_title=None,
    policy_global=None,
    policy_chapter=None,
    character=None,
    previous_episode_text=None,
    neighbor_plots_block=None,
):
    """geminiに渡すプロンプト（指示文とコンテキストの結合）を生成する"""
    task = NovelWritingTask()
    input_data = NovelWritingInput(
        chapter_title=chapter_title,
        episode_title=episode_title,
        plot_content=plot_content,
        novel_title=novel_title,
        policy_global=policy_global,
        policy_chapter=policy_chapter,
        character=character,
        previous_episode_text=previous_episode_text,
        neighbor_plots_block=neighbor_plots_block,
    )
    return task.render_prompt(input_data)


def _write_single_scene(
    chapter_title: str,
    episode: str,
    s_title: str,
    s_plot: str,
    context_written: str,
    prev_context_block: str,
    model: str,
    title: str | None,
    policy_paths: tuple[str, str, str],
    neighbor_plots_block: str | None = None,
) -> str:
    """
    Writes a single scene using agy and returns the generated content.
    """
    policy_global, policy_chapter, character = policy_paths

    task = NovelSceneWritingTask(model=model)
    input_data = NovelSceneWritingInput(
        chapter_title=chapter_title,
        episode_title=episode,
        scene_title=s_title,
        scene_plot=s_plot,
        context_written=context_written,
        prev_context_block=prev_context_block,
        novel_title=title,
        policy_global=policy_global,
        policy_chapter=policy_chapter,
        character=character,
        neighbor_plots_block=neighbor_plots_block,
    )

    def callback(line):
        sys.stdout.write(line)
        sys.stdout.flush()

    try:
        scene_content = task.execute(input_data, callback=callback)
    except AgyClientError as e:
        print(f"Error generating scene: {e}", file=sys.stderr)
        sys.exit(1)

    return scene_content


def _write_step_by_step(
    chapter_title: str,
    episode: str,
    plot_content: str,
    prev_text: str | None,
    model: str,
    title: str | None,
    policy_paths: tuple[str, str, str],
    neighbor_plots_block: str | None = None,
) -> str:
    """
    Executes scene-by-scene incremental writing.
    """
    common_header, scenes = split_scenes(plot_content)

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
        print(
            "No scenes detected in plot. Falling back to single-pass writing.",
            file=sys.stderr,
        )
        policy_global, policy_chapter, character = policy_paths
        task = NovelWritingTask(model=model)
        input_data = NovelWritingInput(
            chapter_title=chapter_title,
            episode_title=episode,
            plot_content=plot_content,
            novel_title=title,
            policy_global=policy_global,
            policy_chapter=policy_chapter,
            character=character,
            previous_episode_text=prev_text,
            neighbor_plots_block=neighbor_plots_block,
        )

        def callback(line):
            sys.stdout.write(line)
            sys.stdout.flush()

        return task.execute(input_data, callback=callback)

    print(f"Detected {len(scenes)} scenes. Starting step-by-step writing...")
    context_written = ""

    for s_idx, (s_title, s_plot) in enumerate(scenes, 1):
        print(f"\n--- Writing Scene {s_idx}/{len(scenes)}: {s_title} ---")
        scene_content = _write_single_scene(
            chapter_title,
            episode,
            s_title,
            s_plot,
            context_written,
            prev_context_block,
            model,
            title,
            policy_paths,
            neighbor_plots_block=neighbor_plots_block,
        )
        print(f"\n[Generated Scene {s_idx} length: {len(scene_content)} chars]")

        if context_written:
            context_written += "\n\n" + scene_content
        else:
            context_written = scene_content

    return context_written


def _perform_self_check(novel_content: str, plot_content: str, model: str, args) -> str:
    """
    Runs policy verification check on generated content and rewrites if needed.
    """
    policy_global, policy_chapter, _ = _resolve_policy_paths(args)
    policy_text = read_file(policy_global)
    policy_macro_text = read_file(policy_chapter)

    return run_self_check(
        novel_content, policy_text, policy_macro_text, plot_content, model
    )


def _print_writing_info(
    chapter_title, episode, model, step_by_step, self_check, output_filename
):
    print(f"Starting writing process for {chapter_title} {episode}...")
    print(f"Model: {model}")
    if step_by_step:
        print("Mode: Step-by-Step (Scene-based)")
    if self_check:
        print("Verification: Policy Self-Check enabled")
    print(f"Output will be saved to: {output_filename}")


def _save_result(output_filename, novel_content):
    # ensure output directory exists
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(novel_content.strip() + "\n")
    print(f"\nSuccess! Novel saved to {output_filename}")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Use Antigravity CLI (agy) to write a novel episode."
    )
    parser.add_argument(
        "--episode", required=True, help="Episode title (e.g., '第1話')"
    )
    default_plot = writer_helper.resolve_novel_file_by_pattern(
        "plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt"
    )
    parser.add_argument(
        "--plot-file", default=default_plot, help="Path to the plot file."
    )
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="Model name (Gemini 3.5 Flash (High), etc.)",
    )
    parser.add_argument("--title", help="Novel title.")
    parser.add_argument("--policy-global", help="Path to global policy file.")
    parser.add_argument("--policy-chapter", help="Path to chapter policy file.")
    parser.add_argument("--character", help="Path to character overview file.")
    parser.add_argument(
        "--step-by-step", action="store_true", help="Write the episode scene by scene."
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Perform self-check/rewrite on output.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Print the generated prompt and exit.",
    )
    parser.add_argument(
        "--include-neighbor-plots",
        action="store_true",
        help="Include plot content of neighboring (previous and next) episodes in the prompt.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    # プロット内容の取得
    chapter_title, plot_content = get_episode_plot(args.plot_file, args.episode)
    if not plot_content:
        print("Failed to get plot content. Exiting.", file=sys.stderr)
        sys.exit(1)

    # 前話の文脈をロード（コンテキストリレー）
    prev_file = get_previous_episode_file(args.plot_file, args.episode)
    prev_text = None
    if prev_file:
        if not args.prompt_only:
            print(f"Loading context from previous episode: {prev_file}")
        full_prev = read_file(prev_file)
        prev_text = "...\n" + full_prev[-1500:] if len(full_prev) > 1500 else full_prev

    # 前後エピソードのプロットブロック取得
    neighbor_plots_block = ""
    if args.include_neighbor_plots:
        prev_plot, next_plot = get_neighboring_episodes_plots(
            args.plot_file, args.episode
        )
        neighbor_plots_block = build_neighbor_plots_block(prev_plot, next_plot)

    if args.prompt_only:
        policy_global, policy_chapter, character = _resolve_policy_paths(args)
        prompt = generate_prompt(
            chapter_title,
            args.episode,
            plot_content,
            novel_title=args.title,
            policy_global=policy_global,
            policy_chapter=policy_chapter,
            character=character,
            previous_episode_text=prev_text,
            neighbor_plots_block=neighbor_plots_block,
        )
        print(prompt)
        sys.exit(0)

    # 出力ファイル名の決定 (novels/X_Y.txt)
    ch_num = extract_numbers(chapter_title) if chapter_title else "0"
    ep_num = extract_numbers(args.episode)
    output_filename = f"novels/{ch_num}_{ep_num}.txt"

    _print_writing_info(
        chapter_title,
        args.episode,
        args.model,
        args.step_by_step,
        args.self_check,
        output_filename,
    )

    novel_content = ""

    try:
        if args.step_by_step:
            policy_paths = _resolve_policy_paths(args)
            novel_content = _write_step_by_step(
                chapter_title,
                args.episode,
                plot_content,
                prev_text,
                args.model,
                args.title,
                policy_paths,
                neighbor_plots_block=neighbor_plots_block,
            )
        else:
            # 一括生成
            policy_global, policy_chapter, character = _resolve_policy_paths(args)
            task = NovelWritingTask(model=args.model)
            input_data = NovelWritingInput(
                chapter_title=chapter_title,
                episode_title=args.episode,
                plot_content=plot_content,
                novel_title=args.title,
                policy_global=policy_global,
                policy_chapter=policy_chapter,
                character=character,
                previous_episode_text=prev_text,
                neighbor_plots_block=neighbor_plots_block,
            )

            def callback(line):
                sys.stdout.write(line)
                sys.stdout.flush()

            novel_content = task.execute(input_data, callback=callback)

        # ポリシーの自己検知チェック & リライト
        if args.self_check and novel_content:
            novel_content = _perform_self_check(
                novel_content, plot_content, args.model, args
            )

        # 結果をファイルに保存
        _save_result(output_filename, novel_content)

    except FileNotFoundError:
        print(
            "Error: 'agy' CLI not found. Please ensure it is installed and in your PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
