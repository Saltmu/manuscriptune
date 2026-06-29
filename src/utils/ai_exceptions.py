class AgyClientError(Exception):
    """Base exception for AgyClient errors."""

    pass


class AgyNotFoundError(AgyClientError):
    """Raised when the 'agy' CLI command is not found."""

    pass
