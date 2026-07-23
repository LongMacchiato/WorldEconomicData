class DBnomicsBrowserError(Exception):
    """Base class for errors that can safely be returned to API clients."""


class ProviderNotFoundError(DBnomicsBrowserError):
    pass


class DatasetNotFoundError(DBnomicsBrowserError):
    pass


class SeriesNotFoundError(DBnomicsBrowserError):
    pass


class UpstreamUnavailableError(DBnomicsBrowserError):
    pass


class UpstreamResponseError(DBnomicsBrowserError):
    pass


class ResultLimitExceededError(DBnomicsBrowserError):
    pass
