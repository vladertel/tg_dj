
class UrlOrNetworkProblem(Exception):
    pass


class UrlProblem(Exception):
    pass


class MediaIsTooLong(Exception):
    pass


class MediaIsTooBig(Exception):
    pass


class BadReturnStatus(Exception):
    pass


class NothingFound(Exception):
    pass


class OnlyOneFound(Exception):
    pass


class UnappropriateArgument(Exception):
    pass


class AskUser(Exception):
    pass
