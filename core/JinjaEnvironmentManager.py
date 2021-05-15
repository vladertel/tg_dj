from typing import List, Union, Dict

from jinja2 import Environment, FileSystemLoader
from utils import make_caption
import os


def f_format_duration(seconds):
    return "{:d}:{:02d}".format(*list(divmod(seconds, 60)))


def f_make_caption(number, forms_list):
    return "%d %s" % (number, make_caption(number, forms_list))


class LocalizationEnvironmentWrapper:
    def __init__(self, config, localization: str):
        """
        :param configparser.ConfigParser config:
        :param str localization:
        """
        self.localization = localization
        self.config = config

    def get_localization(self):
        path = self.config.get("localization", "path",
                               fallback=os.path.join(os.path.dirname(__file__), "localizations"))
        path = os.path.join(path, self.localization)
        return Localization(path)

    def get_env(self, templates_dir: str):
        env = Environment(
            trim_blocks=True,
            lstrip_blocks=True,
            loader=FileSystemLoader(os.path.join(templates_dir, self.localization)),
        )
        env.filters['format_duration'] = f_format_duration
        env.filters['make_caption'] = f_make_caption
        # todo: fix me!
        env.globals["STR_BACK"] = "🔙 Назад"
        env.globals["STR_REFRESH"] = "🔄 Обновить"
        env.globals["STR_REFRESH_SMALL"] = "Обновить"
        env.globals["STR_HOME"] = "🏠 Домой"

# per language
class Localization:
    def __init__(self, path: str):
        """
        :param Language language:
        """
        files = os.listdir(path)
        self._scopes: Dict[str, LocalizationScope] = {}
        for file in files:
            if not os.path.isfile(os.path.join(path, file)):
                continue
            if not file.endswith(".loc"):
                continue
            self._scopes[file.split(".")[0]] = LocalizationScope(os.path.join(path, file), EnLanguage())

    def __getitem__(self, item):
        return self._scopes[item]


class LocalizationScope:
    letters = [chr(ord("A") + i) for i in range(26)] + [chr(ord("a") + i) for i in range(26)]
    digits = [chr(ord("0") + i) for i in range(10)]
    spaces = ['\t', ' ', '\n']
    digits_and_letters = digits + letters

    def __init__(self, scope_path: str, language):
        """
        :param Language language:
        """
        self.language = language
        self.strings = {}
        with open(scope_path) as scope_file:
            self.parse_file(scope_file)

    def parse_file(self, scope_file):
        lines = scope_file.readlines()

        """
        states:
            0 - parsing nothing
            1 - parsing key
            2 - parsing equals
            3 - parsing value 
            4 - parsing value - string
            5 - parsing value - parameter
            6 - parsing value - plural form
            7 - parsing value - plural form - parameter
            8 - parsing value - plural form - equals sign
            9 - parsing value - plural form - values
            10 - parsing value - plural form - values - value
            11 - parsing comment start ('/')
            12 - parsing line comment
            13 - parsing multiline comment
        format: 
            // comment
            /*
            comment
            */
            en:
            asdf = "I have " + $PARAM + { PARAM : "Apple", "Apples", ... } + " in my pocket";
            asdfqwe = "I have " + $PARAM + { PARAM : "Apple", "Apples", ... } + " in my pocket";
            asdsadff = "I have " + $PARAM + { PARAM : "Apple", "Apples", ... } + " in my pocket";
            asdsadgf = "I have " + $PARAM + { PARAM : "Apple", "Apples", ... } + " in my pocket";
            ru:
            asdsadgf = "I have " + $PARAM + { PARAM : "Apple", "Apples", "dhjfgjsdh", ... } + " in my pocket";
            
            ---
            asd = "I have {param} {plur(param, 'Apple', 'Apples', ...)} in my pocket."
        """
        state = 0
        key = ""
        template_value = TemplateValue(self.language)
        template_value_string = ""
        template_plural_form = TemplatePluralForm("")
        should_finalize_value = False
        for line in lines:
            for symbol in line:
                if state == 0:
                    if symbol == "/":
                        state = 11
                    elif symbol in self.letters:
                        state = 1
                        key = symbol
                    elif symbol in self.spaces:
                        continue
                    else:
                        raise 0
                elif state == 1:
                    if symbol in self.digits_and_letters:
                        key += symbol
                    elif symbol in self.spaces:
                        state = 2
                    elif symbol == "=":
                        state = 3
                    else:
                        raise 1
                elif state == 2:
                    if symbol == "=":
                        state = 3
                    elif symbol in self.spaces:
                        continue
                    else:
                        raise 2
                elif state == 3:
                    if symbol in self.spaces:
                        continue
                    if symbol == "+":
                        continue
                    elif symbol == '"':
                        template_value_string = ""
                        state = 4
                    elif symbol == "$":
                        template_value_string = ""
                        state = 5
                    elif symbol == "{":
                        state = 6
                    elif symbol == ";":
                        should_finalize_value = True
                    else:
                        raise 3
                elif state == 4:
                    # todo: bullshit symbols?
                    # todo: \n?
                    if symbol != '"':
                        template_value_string += symbol
                    else:
                        state = 3
                        template_value.add_part(TemplateStringPart(template_value_string))
                        template_value_string = ""
                elif state == 5:
                    if symbol in self.letters:
                        template_value_string += symbol
                    elif symbol == " ":
                        state = 3
                        template_value.add_part(TemplateParameterPart(template_value_string))
                        template_value_string = ""
                    else:
                        raise 5
                elif state == 6:
                    if symbol in self.spaces:
                        continue
                    elif symbol in self.letters:
                        template_value_string = symbol
                        state = 7
                    else:
                        raise 6
                elif state == 7:
                    if symbol in self.letters:
                        template_value_string += symbol
                    elif symbol in self.spaces:
                        template_plural_form = TemplatePluralForm(template_value_string)
                        state = 8
                    elif symbol == ":":
                        template_plural_form = TemplatePluralForm(template_value_string)
                        state = 9
                    else:
                        raise 7
                elif state == 8:
                    if symbol in self.spaces:
                        continue
                    elif symbol == ":":
                        state = 9
                    else:
                        raise 8
                elif state == 9:
                    if symbol in self.spaces:
                        continue
                    elif symbol == '"':
                        template_value_string = ""
                        state = 10
                    elif symbol == "}":
                        if len(template_plural_form.forms) < 2:
                            raise 9.1
                        state = 3
                    else:
                        raise 9
                elif state == 10:
                    if symbol != '"':
                        template_value_string += symbol
                    else:
                        template_plural_form.add_form(template_value_string)
                        template_value_string = ""
                        state = 9
                else:
                    raise -1
                if should_finalize_value:
                    state = 0
                    # todo: some checks here
                    if key in self.strings:
                        raise 123
                    self.strings[key] = template_value

                    template_value = TemplateValue(self.language)
                    template_value_string = ""
                    template_plural_form = TemplatePluralForm("")
                    should_finalize_value = False


class TemplatePart:
    pass

class TemplatePluralForm(TemplatePart):
    def __init__(self, param_name: str):
        self.param_name = param_name
        self.forms: List[str] = []

    def add_form(self, plural_form: str):
        self.forms.append(plural_form)


class TemplateStringPart(TemplatePart):
    def __init__(self, string_part: str):
        self.value = string_part


class TemplateParameterPart(TemplatePart):
    def __init__(self, param_name: str):
        self.param_name = param_name


class Language:
    @staticmethod
    def render(plural_form: TemplatePluralForm, count: Union[int, float]):
        raise 12345


class EnLanguage(Language):
    @staticmethod
    def render(plural_form: TemplatePluralForm, count: Union[int, float]):
        if len(plural_form.forms) != 2:
            raise 53456345
        if count == 1:
            return plural_form.forms[0]
        else:
            return plural_form.forms[1]


class TemplateValue:
    def __init__(self, language: Language):
        self.language = language
        self._parts: List[TemplatePart] = []

    def __call__(self, *args, **kwargs):
        if len(args) > 0:
            raise 123124
        result_string = ""
        for part in self._parts:
            if isinstance(part, TemplatePluralForm):
                if part.param_name not in kwargs:
                    raise 123456789
                count = kwargs[part.param_name]
                if not isinstance(count, int) and not isinstance(count, float):
                    raise 348754309587
                result_string += self.language.render(part, count)
            elif isinstance(part, TemplateStringPart):
                result_string += part.value
            elif isinstance(part, TemplateParameterPart):
                localize_value = False
                param_name = part.param_name
                if param_name.endswith("_LOC"):
                    param_name = param_name[:-4]
                    localize_value = True

                if param_name not in kwargs:
                    raise 123456789

                param_value = kwargs[param_name]
                if localize_value:
                    raise 8357694857

                result_string += str(param_value)
            else:
                raise 6785496874

    def add_part(self, part: TemplatePart):
        self._parts.append(part)
