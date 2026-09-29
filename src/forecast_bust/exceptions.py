class ValidationError(RuntimeError):
    """Raised when source data violates the project contract."""


class RegriddingUnavailableError(ValidationError):
    """Raised when non-identical grids require an unavailable ESMF backend."""
