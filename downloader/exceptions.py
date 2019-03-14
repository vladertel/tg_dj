
class DownloaderException(Exception):
    pass


class UrlOrNetworkProblem(DownloaderException):
    pass


class UrlProblem(DownloaderException):
    pass


class MediaIsTooLong(DownloaderException):
    pass


class MediaIsTooBig(DownloaderException):
    pass


class MediaSizeUnspecified(DownloaderException):
    pass


class BadReturnStatus(DownloaderException):
    pass


class NothingFound(DownloaderException):
    pass


class UnappropriateArgument(DownloaderException):
    pass


class MultipleChoice(DownloaderException):
    pass


class ApiError(DownloaderException):
    pass


class NotAccepted(DownloaderException):
    pass
