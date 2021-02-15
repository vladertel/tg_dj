class ShouldNotBeCalled(Exception):
    pass


# noinspection PyMethodMayBeStatic
class AbstractComponent():

    def bind_core(self, core):
        """
        :param core.DJ_Brain.DjBrain core:
        """
        raise ShouldNotBeCalled()

    def get_name(self) -> str:
        raise ShouldNotBeCalled()
