class NodError(Exception):
    """Base application/domain error."""


class NotFoundError(NodError):
    pass


class ValidationError(NodError):
    pass


class DependencyCycleError(ValidationError):
    pass


class InvalidDependencyError(ValidationError):
    pass


class GitError(NodError):
    pass
