from src.utils.ai_tasks.base import AgyTask, InputT, OutputT
from src.utils.ai_tasks.replacement import (
    BlockReplacementInput,
    BlockReplacementTask,
)
from src.utils.ai_tasks.review import (
    FindingsIntegrationInput,
    FindingsIntegrationTask,
    PlotFindingsIntegrationInput,
    PlotFindingsIntegrationTask,
    ReviewSkillInput,
    ReviewSkillTask,
)
from src.utils.ai_tasks.writing import (
    NovelPolicyCheckInput,
    NovelPolicyCheckTask,
    NovelRewriteInput,
    NovelRewriteTask,
    NovelSceneWritingInput,
    NovelSceneWritingTask,
    NovelWritingInput,
    NovelWritingTask,
)

__all__ = [
    "AgyTask",
    "InputT",
    "OutputT",
    "ReviewSkillInput",
    "ReviewSkillTask",
    "BlockReplacementInput",
    "BlockReplacementTask",
    "FindingsIntegrationInput",
    "FindingsIntegrationTask",
    "PlotFindingsIntegrationInput",
    "PlotFindingsIntegrationTask",
    "NovelWritingInput",
    "NovelWritingTask",
    "NovelSceneWritingInput",
    "NovelSceneWritingTask",
    "NovelPolicyCheckInput",
    "NovelPolicyCheckTask",
    "NovelRewriteInput",
    "NovelRewriteTask",
]
