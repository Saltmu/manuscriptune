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

3. Once a file's formatting is complete, run the following 2 integrated review skills **in parallel** on its formatted text `novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt`. 

**OPTIMIZED SINGLE-PASS RUN:**
To optimize token consumption and utilize the large context capabilities:
- The agent MUST execute each review skill in a **single pass** without splitting the text or calling the prompt multiple times.
- To prevent output truncation, the agent must prioritize finding the most critical issues (severity: `high` or `medium`) and limit the output findings to a **maximum of 15 items** per skill.
- Each skill outputs **YAML format** with `accepted: "n"` fields.

- `logic-consistency-reviewer` -> `novel_check_results/[TARGET_FILE_BASENAME]/02_logic_consistency.yaml`
- `style-expression-reviewer` -> `novel_check_results/[TARGET_FILE_BASENAME]/03_style_expression.yaml`

```bash
echo "Agent: Please execute the above 2 integrated skills in a single pass without chunking. Prioritize key issues and limit findings to a maximum of 15 items for each report."
```

4. **Human Review (per file):** After all 2 `.yaml` files are generated, the user opens each file and changes `accepted: "n"` to `accepted: "y"` for findings they wish to apply. When done, the user instructs the agent to proceed.

5. **Apply Accepted Findings:** The agent reads all `.yaml` files in `novel_check_results/[TARGET_FILE_BASENAME]/`, collects every finding where `accepted: "y"`, and applies the corresponding `suggestion` to `novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt`. The agent should process findings in order of `location` (line number) from bottom to top to avoid line-number shifts. After all accepted findings are applied, save the updated file.
```bash
echo "Agent: Please read all .yaml files in novel_check_results/[TARGET_FILE_BASENAME]/, collect findings with accepted: 'y', and apply their suggestions to 01_formatted.txt in reverse line-number order."
```