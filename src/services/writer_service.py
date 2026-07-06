"""小説執筆のビジネスロジック。

skills/novel-writer-antigravitycli/writer_cli.py と
/api/stream/write, /api/write/prompt の共通実装。
"""

import os
import re
from collections.abc import Callable
from typing import Any

import yaml
from fastapi import HTTPException

from src.utils import path_safety, plot_parser, project_config, project_paths
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
from src.utils.cancellation import CancellationToken
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "Gemini 3.5 Flash (High)"


class WriterServiceError(Exception):
    """プロット未検出やLLM生成失敗など、執筆処理の実行時エラー。"""


def extract_numbers(text: str) -> str:
    """文字列から最初の数字を抽出する（例: '第1章' -> '1'）"""
    match = re.search(r"\d+", text)
    return match.group(0) if match else "0"


def get_episode_plot(plot_file: str, episode_title: str) -> tuple[str | None, str]:
    """指定された話のプロット内容と、それが属する章のタイトルを取得する"""
    if not os.path.exists(plot_file):
        logger.error(f"Plot file not found: {plot_file}")
        return None, ""

    plot_data = plot_parser.parse_plot(plot_file)

    for chapter_data in plot_data:
        chapter_title = chapter_data.get("title", "")
        for ep in chapter_data.get("episodes", []):
            if (
                ep["title"] == episode_title
                or episode_title in ep["title"]
                or episode_title in ep["name"]
            ):
                return chapter_title, "\n".join(ep["content"])

    logger.error(f"Episode '{episode_title}' not found in plot.")
    return None, ""


def get_previous_episode_file(plot_file: str, current_episode_title: str) -> str | None:
    """プロット情報を元に、指定されたエピソードの直前のエピソードの小説ファイルパスを取得する"""
    if not os.path.exists(plot_file):
        return None
    try:
        plot_data = plot_parser.parse_plot(plot_file)
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
            prev_file = project_paths.get_novel_path(f"{prev_ch_num}_{prev_ep_num}.txt")
            if os.path.exists(prev_file):
                return prev_file
    except Exception as e:
        logger.warning(f"Failed to resolve previous episode: {e}")
    return None


def get_neighboring_episodes_plots(
    plot_file: str, current_episode_title: str
) -> tuple[dict | None, dict | None]:
    """指定されたエピソードの「前話」と「後話」のプロット情報を取得する。"""
    if not os.path.exists(plot_file):
        return None, None

    try:
        plot_data = plot_parser.parse_plot(plot_file)
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
        logger.warning(f"Failed to resolve neighboring episodes: {e}")
        return None, None


def build_neighbor_plots_block(prev_plot: dict | None, next_plot: dict | None) -> str:
    if not prev_plot and not next_plot:
        return ""

    block = "【関連エピソードのプロット（参考情報）】\n※前後の展開の整合性を保つための参考情報です。今回の執筆対象ではありません。\n"
    if prev_plot:
        block += f"\n◆ 前話のプロット：{prev_plot['title']}\n{prev_plot['content']}\n"
    if next_plot:
        block += f"\n◆ 後話のプロット：{next_plot['title']}\n{next_plot['content']}\n"
    return block


def split_scenes(plot_content: str) -> tuple[str, list[tuple[str, str]]]:
    """プロット内容を共通のヘッダー情報と、各シーンのプロットに分割する"""
    lines = plot_content.split("\n")
    scenes = []
    current_scene_title = None
    current_scene_lines: list[str] = []

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


def run_self_check(
    novel_content: str,
    policy_text: str,
    policy_macro_text: str,
    plot_content: str,
    model: str,
) -> str:
    """LLMを用いて執筆された本文のポリシー自己チェックと自動リライトを行う"""
    logger.info("Starting self-verification for policy compliance...")

    try:
        check_task = NovelPolicyCheckTask(model=model)
        check_input = NovelPolicyCheckInput(
            novel_content=novel_content,
            policy_text=policy_text,
            policy_macro_text=policy_macro_text,
            plot_content=plot_content,
        )
        yaml_content = check_task.execute(check_input)

        data = yaml.safe_load(yaml_content)
        violations = data.get("violations", []) if isinstance(data, dict) else []

        if not violations:
            logger.info("[Self-Check] No violations found. Compliance OK.")
            return novel_content

        logger.info(
            f"[Self-Check] Found {len(violations)} violations. Starting rewrite..."
        )

        rewrite_task = NovelRewriteTask(model=model)
        rewrite_input = NovelRewriteInput(
            novel_content=novel_content,
            yaml_content=yaml_content,
        )
        rewritten_text = rewrite_task.execute(rewrite_input)
        logger.info("[Self-Check] Rewrite completed successfully.")
        return rewritten_text

    except Exception as e:
        logger.warning(f"Error during self-check or rewrite: {e}")

    return novel_content


def _resolve_policy_paths(
    policy_global: str | None, policy_chapter: str | None, character: str | None
) -> tuple[str, str, str]:
    resolved_policy_global = (
        policy_global
        or project_config.resolve_novel_file_by_pattern(
            "policy_global",
            "*執筆ポリシー_全体*.txt",
            "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt",
        )
    )
    resolved_policy_chapter = (
        policy_chapter
        or project_config.resolve_novel_file_by_pattern(
            "policy_chapter",
            "*執筆ポリシー_第*.txt",
            "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt",
        )
    )
    resolved_character = character or project_config.resolve_novel_file_by_pattern(
        "character",
        "*キャラクター概要*.txt",
        "data/sources/03_1_第1幕キャラクター概要 ver.2.txt",
    )
    return resolved_policy_global, resolved_policy_chapter, resolved_character


def _default_plot_file() -> str:
    return str(
        project_config.resolve_novel_file_by_pattern(
            "plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt"
        )
    )


def _render_prompt(
    chapter_title: str,
    episode_title: str,
    plot_content: str,
    novel_title: str | None = None,
    policy_global: str | None = None,
    policy_chapter: str | None = None,
    character: str | None = None,
    previous_episode_text: str | None = None,
    neighbor_plots_block: str | None = None,
) -> str:
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
    on_line: Callable[[str], None] | None = None,
) -> str:
    """シーン単位でagyを使って本文を生成する。"""
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

    def callback(line: str) -> None:
        if on_line:
            on_line(line)

    try:
        return task.execute(input_data, callback=callback)
    except AgyClientError as e:
        raise WriterServiceError(f"Error generating scene: {e}") from e


def _write_step_by_step(
    chapter_title: str,
    episode: str,
    plot_content: str,
    prev_text: str | None,
    model: str,
    title: str | None,
    policy_paths: tuple[str, str, str],
    neighbor_plots_block: str | None = None,
    on_line: Callable[[str], None] | None = None,
    cancel_token: CancellationToken | None = None,
) -> str:
    """シーンごとに段階的に執筆を実行する。"""
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
        logger.warning(
            "No scenes detected in plot. Falling back to single-pass writing."
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

        def callback(line: str) -> None:
            if on_line:
                on_line(line)

        try:
            return task.execute(input_data, callback=callback)
        except AgyClientError as e:
            raise WriterServiceError(f"Error generating scene: {e}") from e

    logger.info(f"Detected {len(scenes)} scenes. Starting step-by-step writing...")
    context_written = ""

    for s_idx, (s_title, s_plot) in enumerate(scenes, 1):
        if cancel_token:
            cancel_token.check()
        logger.info(f"--- Writing Scene {s_idx}/{len(scenes)}: {s_title} ---")
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
            on_line=on_line,
        )
        logger.info(f"[Generated Scene {s_idx} length: {len(scene_content)} chars]")

        if context_written:
            context_written += "\n\n" + scene_content
        else:
            context_written = scene_content

    return context_written


def _log_writing_start(
    chapter_title: str,
    episode: str,
    model_name: str,
    step_by_step: bool,
    self_check: bool,
    output_filename: str,
) -> None:
    logger.info(f"Starting writing process for {chapter_title} {episode}...")
    logger.info(f"Model: {model_name}")
    if step_by_step:
        logger.info("Mode: Step-by-Step (Scene-based)")
    if self_check:
        logger.info("Verification: Policy Self-Check enabled")
    logger.info(f"Output will be saved to: {output_filename}")


def _generate_novel_content(
    chapter_title: str,
    episode: str,
    plot_content: str,
    prev_text: str | None,
    model_name: str,
    title: str | None,
    policy_paths: tuple[str, str, str],
    step_by_step: bool,
    neighbor_plots_block: str,
    on_line: Callable[[str], None] | None,
    cancel_token: CancellationToken | None,
) -> str:
    if step_by_step:
        return _write_step_by_step(
            chapter_title,
            episode,
            plot_content,
            prev_text,
            model_name,
            title,
            policy_paths,
            neighbor_plots_block=neighbor_plots_block,
            on_line=on_line,
            cancel_token=cancel_token,
        )

    policy_global, policy_chapter, character = policy_paths
    task = NovelWritingTask(model=model_name)
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

    def callback(line: str) -> None:
        if on_line:
            on_line(line)

    try:
        return task.execute(input_data, callback=callback)
    except AgyClientError as e:
        raise WriterServiceError(f"Error generating scene: {e}") from e


class WriterService:
    """writer_cli.py と /api/stream/write, /api/write/prompt の共通実装。"""

    def resolve_episode_output_path(
        self, episode: str, plot_file: str | None = None
    ) -> tuple[str, str]:
        """エピソード名（例：「第1話」）とプロットファイルから、
        小説ファイルの絶対パスと basename を解決する唯一の実装。
        """
        plot_filepath = plot_file if plot_file else _default_plot_file()

        if not os.path.isabs(plot_filepath):
            plot_filepath = os.path.abspath(
                project_paths.get_source_path(os.path.basename(plot_filepath))
            )
        elif not path_safety.is_within(project_paths.get_sources_dir(), plot_filepath):
            raise HTTPException(status_code=403, detail="Invalid plot file path.")

        plot_data = plot_parser.parse_plot(plot_filepath)

        chapter_title = None
        for chapter_data in plot_data:
            c_title = chapter_data.get("title", "")
            for ep in chapter_data.get("episodes", []):
                if (
                    ep["title"] == episode
                    or episode in ep["title"]
                    or episode in ep["name"]
                ):
                    chapter_title = c_title
                    break
            if chapter_title:
                break

        ch_num = extract_numbers(chapter_title) if chapter_title else "0"
        ep_num = extract_numbers(episode)
        basename = f"{ch_num}_{ep_num}"
        novel_path = os.path.abspath(project_paths.get_novel_path(f"{basename}.txt"))
        return novel_path, basename

    def generate_prompt(
        self,
        *,
        episode: str,
        plot_file: str | None = None,
        model: str | None = None,
        title: str | None = None,
        policy_global: str | None = None,
        policy_chapter: str | None = None,
        character: str | None = None,
        include_neighbor_plots: bool = False,
        **_unused: Any,
    ) -> str:
        """--prompt-only 相当。副作用・LLM呼び出しなし。"""
        plot_filepath = plot_file or _default_plot_file()
        raw_chapter_title, plot_content = get_episode_plot(plot_filepath, episode)
        if not plot_content:
            raise WriterServiceError("Failed to get plot content.")
        chapter_title = raw_chapter_title or ""

        prev_file = get_previous_episode_file(plot_filepath, episode)
        prev_text = self._load_previous_text(prev_file)

        neighbor_plots_block = ""
        if include_neighbor_plots:
            prev_plot, next_plot = get_neighboring_episodes_plots(
                plot_filepath, episode
            )
            neighbor_plots_block = build_neighbor_plots_block(prev_plot, next_plot)

        resolved_policy_global, resolved_policy_chapter, resolved_character = (
            _resolve_policy_paths(policy_global, policy_chapter, character)
        )
        return _render_prompt(
            chapter_title,
            episode,
            plot_content,
            novel_title=title,
            policy_global=resolved_policy_global,
            policy_chapter=resolved_policy_chapter,
            character=resolved_character,
            previous_episode_text=prev_text,
            neighbor_plots_block=neighbor_plots_block,
        )

    def execute(
        self,
        *,
        episode: str,
        plot_file: str | None = None,
        model: str | None = None,
        title: str | None = None,
        policy_global: str | None = None,
        policy_chapter: str | None = None,
        character: str | None = None,
        step_by_step: bool = False,
        self_check: bool = False,
        include_neighbor_plots: bool = False,
        cancel_token: CancellationToken | None = None,
        on_line: Callable[[str], None] | None = None,
        **_unused: Any,
    ) -> str:
        """1話分の小説本文を生成しファイルへ保存する。戻り値は保存先の絶対パス。"""
        model_name = model or DEFAULT_MODEL
        plot_filepath = plot_file or _default_plot_file()

        raw_chapter_title, plot_content = get_episode_plot(plot_filepath, episode)
        if not plot_content:
            raise WriterServiceError("Failed to get plot content.")
        chapter_title = raw_chapter_title or ""

        prev_file = get_previous_episode_file(plot_filepath, episode)
        prev_text = self._load_previous_text(prev_file)
        if prev_file:
            logger.info(f"Loading context from previous episode: {prev_file}")

        neighbor_plots_block = ""
        if include_neighbor_plots:
            prev_plot, next_plot = get_neighboring_episodes_plots(
                plot_filepath, episode
            )
            neighbor_plots_block = build_neighbor_plots_block(prev_plot, next_plot)

        policy_paths = _resolve_policy_paths(policy_global, policy_chapter, character)

        ch_num = extract_numbers(chapter_title) if chapter_title else "0"
        ep_num = extract_numbers(episode)
        output_filename = os.path.abspath(
            project_paths.get_novel_path(f"{ch_num}_{ep_num}.txt")
        )
        _log_writing_start(
            chapter_title,
            episode,
            model_name,
            step_by_step,
            self_check,
            output_filename,
        )

        if cancel_token:
            cancel_token.check()

        novel_content = _generate_novel_content(
            chapter_title,
            episode,
            plot_content,
            prev_text,
            model_name,
            title,
            policy_paths,
            step_by_step,
            neighbor_plots_block,
            on_line,
            cancel_token,
        )

        if cancel_token:
            cancel_token.check()

        if self_check and novel_content:
            resolved_policy_global, resolved_policy_chapter, _character = policy_paths
            policy_text = read_file(resolved_policy_global)
            policy_macro_text = read_file(resolved_policy_chapter)
            novel_content = run_self_check(
                novel_content, policy_text, policy_macro_text, plot_content, model_name
            )

        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(novel_content.strip() + "\n")
        logger.info(f"Success! Novel saved to {output_filename}")
        return output_filename

    @staticmethod
    def _load_previous_text(prev_file: str | None) -> str | None:
        if not prev_file:
            return None
        full_prev = read_file(prev_file)
        return "...\n" + full_prev[-1500:] if len(full_prev) > 1500 else full_prev
