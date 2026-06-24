---
description: Run the entire novel review pipeline (Formatting -> Parallel Review Skills) in parallel across multiple files and save the results in `novel_check_results`.
---

# Novel Review Pipeline

This workflow executes all available skills for one or more novel files. It is designed to be highly parallel: multiple files can be processed independently, and for each file, multiple review skills are executed concurrently. After reviews complete, the user selects which findings to accept, and the agent applies them.

> [!TIP]
> **Context Caching:**
> Since multiple review skills are executed on the same formatted chapter and settings context, the executing agent system or API runtime should enable **Context Caching** to cache the common system prompts, settings context, and formatted chapter text. This dramatically reduces API token consumption and costs.

// turbo-all

0. Identify all target novel files (e.g., all `.txt` files in the `novels/` directory). **Steps 1-3 should be executed for each file independently and in parallel.**

1. Create a subdirectory for the results within `novel_check_results` named after the target file (e.g., `novel_check_results/[TARGET_FILE_BASENAME]`).
```bash
mkdir -p novel_check_results/[TARGET_FILE_BASENAME]
```

2. Format the novel and save the output. Please replace `[TARGET_FILE]` with the path to the novel text file you want to review. **Important:** Wait for this step to complete for the *specific file* before proceeding to the filtering step for that same file.
```bash
echo "Agent: Please run novel-formatter on [TARGET_FILE] and save to novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt. Wait for completion of this file's formatting."
```

2.5. Run the keyword-based RAG filter script to generate a compact settings context file.
```bash
poetry run python src/filter_context.py novel_check_results/[TARGET_FILE_BASENAME]/01_formatted.txt novel_check_results/[TARGET_FILE_BASENAME]/01_filtered_context.txt
```

3. Once a file's formatting and context filtering are complete, execute the parallel review using subagents:

**SUBAGENT PARALLEL EXECUTION:**
The main agent MUST spawn two specialist subagents in parallel to perform the review:
- **Logic Auditor (Subagent)**: Runs the `logic-consistency-reviewer` skill on `01_formatted.txt` using `01_filtered_context.txt` as settings reference. Saves findings to `novel_check_results/[TARGET_FILE_BASENAME]/02_logic_consistency.yaml`.
- **Style Editor (Subagent)**: Runs the `style-expression-reviewer` skill on `01_formatted.txt`. Saves findings to `novel_check_results/[TARGET_FILE_BASENAME]/03_style_expression.yaml`.

Use the `invoke_subagent` tool to spawn these subagents concurrently.

```bash
echo "Agent: Please spawn the Logic Auditor and Style Editor subagents in parallel to review 01_formatted.txt."
```

3.5. **Consensus & Conflict Resolution (Merge):**
After both subagents complete their reviews, the main agent (acting as Editor-in-Chief) must read both YAML files and perform consensus merging:
- **Remove Duplicates:** Consolidate similar findings on the same lines.
- **Resolve Conflicts:** Verify that the Style Editor's suggestions do not violate the world-building rules or character profiles identified by the Logic Auditor. If a conflict occurs, prioritize the logic or adjust the style suggestion to align with the setting rules.
- **Filter by Severity:** Keep only critical findings (severity: `high` or `medium`) and limit the consolidated findings to a **maximum of 20-25 items**.
- **Consolidated Output:** Save the merged findings as `novel_check_results/[TARGET_FILE_BASENAME]/00_integrated_findings.yaml`. Optionally, create a clean markdown summary report at `novel_check_results/[TARGET_FILE_BASENAME]/00_integrated_report.md`.

```bash
echo "Agent: Read 02_logic_consistency.yaml and 03_style_expression.yaml, resolve any logic-style conflicts, and save the merged findings to 00_integrated_findings.yaml."
```

4. **Interactive Reflective Review (Chat/CLI):**
   The main agent reviews the output and presents a summary of the merged findings to the user in the chat, asking: "Would you like to apply these review results?"
   The user can reply in the chat with a list of IDs to apply (e.g., "Apply 1 and 3" or "Apply INT-001, INT-003"), "Apply all", or "Discard".
   
   Alternatively, the user can run the interactive CLI script directly in their terminal to review and apply them step-by-step:
   ```bash
   poetry run apply-findings --dir novel_check_results/[TARGET_FILE_BASENAME] --interactive
   ```

5. **Apply Selection (Automated via Script):**
   Once the user specifies which findings to apply in the chat (or decides to apply all), the agent runs the `apply_findings.py` script with the corresponding mode to modify the text accurately and update the YAML status.
   - To apply specific IDs selected by the user:
     ```bash
     poetry run apply-findings --dir novel_check_results/[TARGET_FILE_BASENAME] --accept-ids INT-001,INT-003
     ```
   - To apply all findings marked as `accepted: "y"` (if the user edited the YAML file manually):
     ```bash
     poetry run apply-findings --dir novel_check_results/[TARGET_FILE_BASENAME] --auto
     ```
