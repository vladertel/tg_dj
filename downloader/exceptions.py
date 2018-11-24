
class UrlOrNetworkProblem(Exception):
    pass


class UrlProblem(Exception):
    pass


class MediaIsTooLong(Exception):
    pass


class MediaIsTooBig(Exception):
    pass


class MediaSizeUnspecified(Exception):
    pass


class BadReturnStatus(Exception):
    pass


class NothingFound(Exception):
    pass


class UnappropriateArgument(Exception):
    pass


class MultipleChoice(Exception):
    pass


class ApiError(Exception):
    pass


class NotAccepted(Exception):
    pass
