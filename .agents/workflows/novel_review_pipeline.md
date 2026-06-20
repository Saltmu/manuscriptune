---
description: Run the entire novel review pipeline (Formatting -> Parallel Review Skills) in parallel across multiple files and save the results in `novel_check_results`.
---

# Novel Review Pipeline

This workflow executes all available skills for one or more novel files. It is designed to be highly parallel: multiple files can be processed independently, and for each file, multiple review skills are executed concurrently. After reviews complete, the user selects which findings to accept, and the agent applies them.

// turbo-all

0. Identify all target novel files (e.g., all `.txt` files in the `novels/` directory). **Steps 1-3 should be executed for each file independently and in parallel.**

1. Create a subdirectory for the results within `novel_check_results` named after the target file (e.g., `novel_check_results/[TARGET_FILE_BASENAME]`).
```bash
mkdir -p novel_check_results/[TARGET_FILE_BASENAME]
```

2. Format the novel and save the output. Please replace `[TARGET_FILE]` with the path to the novel text file you want to review. **Important:** Wait for this step to complete for the *specific file* before proceeding to Step 3 for that same file, as the review skills depend on its formatted text.
```bash
echo "Agent: Please run novel-formatter on [TARGET_FILE] and save to novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt. Wait for completion of this file's formatting."
```

3. Once a file's formatting is complete, run the following 7 review skills **in parallel** on its formatted text `novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt`. 

**CRITICAL INSTRUCTION FOR LLM LIMITS:**
To avoid output token limits and ensure multiple findings are generated per skill without being truncated:
- The agent MUST execute the prompt for each skill **multiple times** (e.g., "Find the first 3 issues", then "Find the next 3 issues excluding the previous ones") OR split the target text into halves/thirds and review each chunk independently.
- The agent must then consolidate these multiple outputs into a single YAML file per skill.
- Each skill outputs **YAML format** with `accepted: "n"` fields.

- `world-logic-guard` -> `novel_check_results/[TARGET_FILE_BASENAME]/02_world_logic.yaml`
- `consistency-checker` -> `novel_check_results/[TARGET_FILE_BASENAME]/03_consistency.yaml`
- `show-dont-tell-enhancer` -> `novel_check_results/[TARGET_FILE_BASENAME]/04_show_dont_tell.yaml`
- `foreshadowing-tracker` -> `novel_check_results/[TARGET_FILE_BASENAME]/05_foreshadowing.yaml`
- `plot-pacing-analyzer` -> `novel_check_results/[TARGET_FILE_BASENAME]/06_pacing.yaml`
- `rhythm-vocabulary-optimizer` -> `novel_check_results/[TARGET_FILE_BASENAME]/07_rhythm.yaml`
- `character-voice-checker` -> `novel_check_results/[TARGET_FILE_BASENAME]/08_character_voice.yaml`

```bash
echo "Agent: Please execute the above 7 skills. For each skill, use split-prompting or text-chunking to bypass token limits, gather multiple findings, and merge them into the final YAML reports for [TARGET_FILE_BASENAME]."
```

4. **Human Review (per file):** After all 7 `.yaml` files are generated, the user opens each file and changes `accepted: "n"` to `accepted: "y"` for findings they wish to apply. When done, the user instructs the agent to proceed.

5. **Apply Accepted Findings:** The agent reads all `.yaml` files in `novel_check_results/[TARGET_FILE_BASENAME]/`, collects every finding where `accepted: "y"`, and applies the corresponding `suggestion` to `novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt`. The agent should process findings in order of `location` (line number) from bottom to top to avoid line-number shifts. After all accepted findings are applied, save the updated file.
```bash
echo "Agent: Please read all .yaml files in novel_check_results/[TARGET_FILE_BASENAME]/, collect findings with accepted: 'y', and apply their suggestions to 01_formatted.txt in reverse line-number order."
```