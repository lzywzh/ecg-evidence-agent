class AppError(Exception):
    """Base class for expected application failures."""


class DocumentImportError(AppError):
    pass


class SourceConflictError(AppError):
    pass


class StorageError(AppError):
    pass
