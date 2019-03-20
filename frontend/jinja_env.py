from jinja2 import Environment, FileSystemLoader
from utils import make_caption
import os


def f_format_duration(seconds):
    return "{:d}:{:02d}".format(*list(divmod(seconds, 60)))


def f_make_caption(number, forms_list):
    return "%d %s" % (number, make_caption(number, forms_list))


env = Environment(
    trim_blocks=True,
    lstrip_blocks=True,
    loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tg_templates")),
)
env.filters['format_duration'] = f_format_duration
env.filters['make_caption'] = f_make_caption

env.globals["STR_BACK"] = "🔙 Назад"
env.globals["STR_REFRESH"] = "🔄 Обновить"
env.globals["STR_REFRESH_SMALL"] = "Обновить"
env.globals["STR_HOME"] = "🏠 Домой"
