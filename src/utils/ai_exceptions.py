class AgyClientError(Exception):
    """Base exception for AgyClient errors."""

    pass


class AgyNotFoundError(AgyClientError):
    """Raised when the 'agy' CLI command is not found."""

    pass


class PipelineError(Exception):
    """Base exception for pipeline operations."""

    pass


class FormattingError(PipelineError):
    """Raised when formatting a draft fails."""

    pass


class ContextFilteringError(PipelineError):
    """Raised when filtering draft context fails."""

    pass


class ReviewSkillExecutionError(PipelineError):
    """Raised when a specific review skill execution fails."""

    pass


class IntegrationError(PipelineError):
    """Raised when integrating findings fails."""

    pass
