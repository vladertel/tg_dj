from jinja2 import Environment
from utils import make_caption


def f_format_duration(seconds):
    return "{:d}:{:02d}".format(*list(divmod(seconds, 60)))


def f_make_caption(number, forms_list):
    return "%d %s" % (number, make_caption(number, forms_list))


env = Environment(
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters['format_duration'] = f_format_duration
env.filters['make_caption'] = f_make_caption
