import telebot
import threading
from queue import Queue
import re
import peewee
from time import sleep
import time
from .jinja_env import env

from .private_config import token


compiled_regex = re.compile(r"^\d+")

help_message = """Приветствую тебя, %ЮЗЕРНЕЙМ%!

Этот бот позволяет тебе управлять музыкой, которая играет на нашем общем празднике.

Во-первых, ты можешь добавить в плейлист твои любимые треки. Для этого можно:
1. Воспользоваться кнопкой поиска музыки ниже
2. Отправить ссылку на видео на ютубе (например https://www.youtube.com/watch?v=dQw4w9WgXcQ)
3. Отправить ссылку на любой mp3-файл
4. Отправить сам файл с музыкой 

Во-вторых, ты можешь голосовать за/против музыки в очереди.

Если у вас исчезло меню, то вернуть его на место можно командой /start
"""

STR_BACK = "🔙 Назад"
STR_REFRESH = "🔄 Обновить"


db = peewee.SqliteDatabase("db/telegram_bot.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class User(BaseModel):
    tg_id = peewee.IntegerField(unique=True)
    core_id = peewee.IntegerField()
    login = peewee.CharField(null=True)
    first_name = peewee.CharField(null=True)
    last_name = peewee.CharField(null=True)
    menu_message_id = peewee.IntegerField(null=True)
    menu_chat_id = peewee.IntegerField(null=True)

    def full_name(self):
        return self.first_name + " " + self.last_name


db.connect()


class TgFrontend:

    def __init__(self):
        self.bot = telebot.TeleBot(token)
        self.botThread = threading.Thread(daemon=True, target=self.bot_init)
        self.botThread.start()
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.brainThread = threading.Thread(daemon=True, target=self.brain_listener)
        self.brainThread.start()
        self.init_handlers()
        self.init_callbacks()

        self.generators = {}
        self.gen_cnt = 0

        self.bamboozled_users = []

# INIT #####
    def bot_init(self):
        while True:
            try:
                print("INFO [Bot]: Loading bot")
                self.bot.polling(none_stop=True)
            except Exception as e:
                print("ERROR [Bot]: CONNECTION PROBLEM")
                print(e)
                sleep(15)

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(lambda data: self.tg_handler(data, self.start_handler))
        self.bot.message_handler(commands=['broadcast'])(self.broadcast_to_all_users)
        self.bot.message_handler(commands=['get_info'])(self.get_user_info)
        self.bot.message_handler(commands=['stop_playing', 'stop'])(lambda data: self.tg_handler(data, self.stop_playing))
        self.bot.message_handler(commands=['skip_song', 'skip'])(lambda data: self.tg_handler(data, self.skip_song))
        self.bot.message_handler(commands=['/'])(lambda x: True)

        self.bot.message_handler(content_types=['text'])(lambda data: self.tg_handler(data, self.download))
        self.bot.message_handler(content_types=['audio'])(lambda data: self.tg_handler(data, self.add_audio_file))
        self.bot.message_handler(content_types=['file', 'photo', 'document'])(self.file_handler)
        self.bot.message_handler(content_types=['sticker'])(self.sticker_handler)

    def init_callbacks(self):
        self.bot.callback_query_handler(func=lambda x: x.data[0:2] == "//")(lambda x: True)
        self.bot.callback_query_handler(func=lambda x: True)(lambda data: self.tg_handler(data, self.callback_query))

        self.bot.inline_handler(func=lambda x: True)(lambda data: self.tg_handler(data, self.search))
        self.bot.chosen_inline_handler(func=lambda x: True)(lambda data: self.tg_handler(data, self.search_select))

    def cleanup(self):
        pass


#######################
# TG CALLBACK HANDLERS
    def tg_handler(self, data, method):
        try:
            user = User.get(User.tg_id == data.from_user.id)
        except peewee.DoesNotExist:
            method = self.init_user
            user = None

        gen = method(data, user)
        request_id = self.gen_cnt
        self.gen_cnt += 1
        self.generators[request_id] = gen

        try:
            action = next(gen)
            action["request_id"] = request_id
            action["user_id"] = getattr(user, "core_id", None)
            self.output_queue.put(action)
        except StopIteration:
            pass

    def callback_query(self, data, user):
        user.menu_message_id = data.message.message_id
        user.menu_chat_id = data.message.chat.id
        user.save()

        path = data.data.split(":")
        if len(path) == 0:
            print("ERROR [Bot]: Bad menu path: " + str(path))
            return

        if path[0] == "main":
            response = yield {"action": "get_status"}
            self.send_menu_main(response, user)
        elif path[0] == "queue":
            page = int(path[1])
            response = yield {"action": "get_queue", "page": page}
            self.send_menu_queue(response, user)
        elif path[0] == "song":
            sid = int(path[1])
            response = yield {"action": "get_song_info", "song_id": sid}
            if response["song_id"] is not None:
                self.send_menu_song(response, user)
            else:
                response = yield {"action": "get_queue", "page": response["page"]}
                self.send_menu_queue(response, user)
        elif path[0] == "vote":
            sign = path[1]
            sid = int(path[2])
            if sign == "up":
                yield {"action": "vote", "sign": "+", "song_id": sid}
            else:
                yield {"action": "vote", "sign": "-", "song_id": sid}
            response = yield {"action": "get_song_info", "song_id": sid}
            self.send_menu_song(response, user)
        elif path[0] == "admin":
            path.pop(0)
            yield from self.admin_query(path, user)
        else:
            print('ERROR [Bot]: Callback query is not supported:', str(path))

    def admin_query(self, path, user):
        print('INFO [Bot]: Admin query from user %d: %s' % (user.tg_id, str(path)))
        if path[0] == "skip_song":
            yield {"action": "skip_song"}
            response = yield {"action": "get_status"}
            self.send_menu_main(response, user)
        elif path[0] == 'stop_playing':
            yield {"action": "stop_playing"}
            response = yield {"action": "get_status"}
            self.send_menu_main(response, user)
        elif path[0] == "delete":
            sid = int(path[1])
            response = yield {"action": "remove_song", "song_id": sid}
            response = yield {"action": "get_queue", "page": response["pos"] // 10}
            self.send_menu_queue(response, user)
        elif path[0] == "list_users":
            page = int(path[1])
            response = yield {"action": "get_users_list", "page": page}
            self.send_menu_admin_list_users(response, user)
        elif path[0] == "user_info":
            uid = int(path[1])
            response = yield {"action": "get_user_info", "handled_user_id": uid}
            if response["handled_user"] is not None:
                self.send_menu_admin_user(response, user)
            else:
                print("ERROR [Core]: User does not exists: can't obtain user info")
                response = yield {"action": "get_users_list", "page": response["page"]}
                self.send_menu_admin_list_users(response, user)
        elif path[0] == "ban_user":
            uid = int(path[1])
            yield {"action": "ban_user", "handled_user_id": uid}
            response = yield {"action": "get_user_info", "handled_user_id": uid}
            self.send_menu_admin_user(response, user)
        elif path[0] == "unban_user":
            uid = int(path[1])
            yield {"action": "unban_user", "handled_user_id": uid}
            response = yield {"action": "get_user_info", "handled_user_id": uid}
            self.send_menu_admin_user(response, user)
        else:
            print('ERROR [Core]: Admin query is not supported:', str(path))

    def search(self, data, user):
        query = data.query.lstrip()

        response = yield {
            "action": "search",
            "query": query,
        }

        state = response["state"]
        if state == "user_message" or state == "error":
            self.bot.send_message(user.tg_id, response["message"])
            return

        results = response["results"]

        results_articles = []
        for song in results:
            results_articles.append(telebot.types.InlineQueryResultArticle(
                id=song['downloader'] + " " + song['id'],
                title=song['artist'],
                description=song['title'] + " {:d}:{:02d}".format(*list(divmod(song["duration"], 60))),
                input_message_content=telebot.types.InputTextMessageContent(
                    "// " + song['artist'] + " - " + song['title']
                ),
            ))

        self.bot.answer_inline_query(data.id, results_articles)

    def search_select(self, data, user):
        downloader, result_id = data.result_id.split(" ")
        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")

        response = yield {
            "action": "download",
            "downloader": downloader,
            "result_id": result_id,
        }

        while True:
            state = response["state"]
            if state == "user_message" or state == "error":
                print("DEBUG [Bot]: EDIT MESSAGE: " + str(response["message"]))
                self.bot.edit_message_text(response["message"], reply.chat.id, reply.message_id)
            elif state == "no_dl_handler":
                self.bot.edit_message_text("Ошибка: обработчик не найден", reply.chat.id, reply.message_id)
            elif state == "download_done":
                break
            response = yield

    def download(self, message, user):
        text = message.text

        if re.search(r'^@\w+ ', text) is not None:
            self.bot.send_message(user.tg_id, "Выберите из интерактивного меню, пожалуйста."
                                              "Интерактивное меню появляется во время ввода сообщения")
            return

        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")

        response = yield {
            "action": "download",
            "text": text,
        }

        while True:
            state = response["action"]
            if state == "user_message" or state == "error":
                self.bot.edit_message_text(response["message"], reply.chat.id, reply.message_id)
            elif state == "no_dl_handler":

                kb = telebot.types.InlineKeyboardMarkup(row_width=2)
                kb.row(telebot.types.InlineKeyboardButton(
                    text="🔍 " + text,
                    switch_inline_query_current_chat=text,
                ))

                self.bot.edit_message_text("Запрос не распознан. Нажмите на кнопку ниже, чтобы включить поиск",
                                           reply.chat.id, reply.message_id)
                self.bot.edit_message_reply_markup(reply.chat.id, reply.message_id, reply_markup=kb)
            elif state == "download_done":
                break
            response = yield

    def add_audio_file(self, message, user):
        file_info = self.bot.get_file(message.audio.file_id)

        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")

        response = yield {
            "action": "download",
            "file": message.audio.file_id,
            "duration": message.audio.duration,
            "file_size": message.audio.file_size,
            "file_info": file_info,
            "artist": message.audio.performer or "",
            "title": message.audio.title or "",
        }

        while True:
            state = response["action"]
            if state == "user_message" or state == "error":
                self.bot.edit_message_text(response["message"], reply.chat.id, reply.message_id)
            elif state == "no_dl_handler":
                self.bot.edit_message_text("Ошибка: обработчик не найден", reply.chat.id, reply.message_id)
            elif state == "download_done":
                break
            response = yield


# MENU RELATED #####
    def remove_old_menu(self, user):

        # self.bot.edit_message_reply_markup(
        #     user.menu_chat_id, user.menu_message_id,
        #     reply_markup=telebot.types.InlineKeyboardMarkup()
        # )

        if user.menu_message_id is not None and user.menu_chat_id is not None:
            try:
                self.bot.delete_message(user.menu_chat_id, user.menu_message_id)
            except Exception as e:
                print("WARNING [Bot]: delete_message exception: " + str(e))

    def build_markup(self, text):
        lines = text.splitlines(False)
        btn_re = re.compile(r"(?:^|\|\|)\s*(?P<text>(?:[^|\\]|\\\|)+)|"
                            r"(?P<attr>(?:[^|\\=]|\\.)+)\s*=\s*(?P<val>(?:[^|\\]|\\.)*)")

        markup = telebot.types.InlineKeyboardMarkup()

        for line in lines:
            line = line.strip()
            if line == "":
                continue

            matches = btn_re.findall(line)

            buttons = []
            btn = None

            for match in matches:
                text = match[0].strip()
                if text != "":
                    btn = {"text": text}
                    buttons.append(btn)
                else:
                    btn[match[1].strip()] = match[2].strip()

            m_row = []
            for b in buttons:
                if "callback_data" in b:
                    m_row.append(telebot.types.InlineKeyboardButton(
                        text=b["text"],
                        callback_data=b["callback_data"]
                    ))
                elif "switch_inline_query_current_chat" in b:
                    m_row.append(telebot.types.InlineKeyboardButton(
                        text=b["text"],
                        switch_inline_query_current_chat=b["switch_inline_query_current_chat"]
                    ))

            markup.row(*m_row)
        return markup

    def send_menu_main(self, data, user):
        menu_template = """
            {% if superuser %}
                {% if now_playing is not none %}
                    ⏹ Остановить | callback_data=admin:stop_playing || ▶️ Переключить | callback_data=admin:skip_song
                {% else %}
                    ▶️ Запустить | callback_data=admin:skip_song
                {% endif %}
            {% endif %}
            {% if queue_len %}
                📂 Очередь: {{ queue_len | make_caption(['трек', '', 'а', 'а', 'а', 'ов']) }} | callback_data=queue:0
            {% endif %}
            {% if superuser %}
                👥 Пользователи | callback_data=admin:list_users:0
            {% endif %}
            🔍 Поиск музыки | switch_inline_query_current_chat=
            🔄 Обновить | callback_data=main
        """

        msg_template = """
            {% if now_playing is not none %}
                🔊 [{{ now_playing["played"] | format_duration }} / {{ now_playing["duration"] | format_duration }}]    👤 {{ now_playing["author_name"] }}
                {{ now_playing["title"] }}\n
            {% endif %}
            {% if superuser and next_in_queue is not none %}
                Следующий трек:
                ⏱ {{ next_in_queue.duration | format_duration }}    👤 {{ next_in_queue.author }}
                {{ next_in_queue.title }}
            {% endif %}
        """

        superuser = data["superuser"]
        queue_len = data["queue_len"]

        now_playing = data["now_playing"]
        if now_playing is not None:
            if now_playing["user_id"] is not None:
                track_author = User.get(User.core_id == now_playing["user_id"])
                now_playing["author_name"] = track_author.full_name()
            else:
                now_playing["author_name"] = "Студсовет"

            now_playing["played"] = int(time.time() - now_playing["start_time"])

        next_in_queue = data["next_in_queue"]
        if superuser and next_in_queue is not None:
            if next_in_queue.user is not None:
                track_author = User.get(User.core_id == next_in_queue.user)
                next_in_queue.author = track_author.full_name()
            else:
                next_in_queue.author = "Студсовет"

        template = env.from_string(menu_template)
        rendered = template.render(now_playing=now_playing, superuser=superuser, queue_len=queue_len)
        kb = self.build_markup(rendered)

        template = env.from_string('\n'.join([l.strip() for l in msg_template.splitlines(False)]))
        message_text = template.render(now_playing=now_playing, next_in_queue=next_in_queue, superuser=superuser)

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_queue(self, data, user):
        page = data["page"]
        songs_list = data["songs_list"]
        is_last_page = data["is_last_page"]

        if not songs_list:
            message_text = "В очереди воспроизведения ничего нет"
        else:
            message_text = "Очередь воспроизведения\n" \
                           "Выбери песню, чтобы посмотреть подробную информацию или проголосовать"

        kb = telebot.types.InlineKeyboardMarkup(row_width=3)
        for song in songs_list:
            kb.row(telebot.types.InlineKeyboardButton(text=song.title, callback_data="song:%d" % song.id))

        nav = []
        if page > 0 or not is_last_page:
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if page <= 0 else "⬅️",
                callback_data="//" if page <= 0 else "queue:%d" % (page - 1),
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="Стр. %d" % (page + 1),
                callback_data="//"
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if is_last_page else "➡️",
                callback_data="//" if is_last_page else "queue:%d" % (page + 1),
            ))
            kb.row(*nav)

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="main"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="queue:%d" % page))

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_song(self, data, user):
        superuser = data['superuser']
        sid = data["song_id"]
        duration = data["duration"]
        rating = data["rating"]
        position = data["position"]
        page = data["page"]
        title = data["title"]

        str_duration = "{:d}:{:02d}".format(*list(divmod(duration, 60)))
        base_str = "Песня: {}\nПродолжительность: {}\nРейтинг: {:d}\nМесто в очереди: {:d}"
        message_text = base_str.format(title, str_duration, rating, position)
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(text="👍", callback_data="vote:up:%s" % sid),
               telebot.types.InlineKeyboardButton(text="👎", callback_data="vote:down:%s" % sid))

        if superuser:
            kb.row(telebot.types.InlineKeyboardButton(text="Удалить", callback_data="admin:delete:%s" % sid))

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="queue:%d" % page),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="song:%s" % sid))

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_admin_list_users(self, data, user):
        page = data["page"]
        users_list = data["users_list"]
        users_cnt = data["users_cnt"]
        is_last_page = data["is_last_page"]

        if users_cnt == 0:
            message_text = "Нет ни одного пользователя"
        else:
            message_text = "Количество пользователей: %d" % users_cnt

        users_ids = [u.id for u in users_list]
        users = User.select().filter(User.core_id.in_(users_ids))

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        for u in users:
            button_text = str(u.tg_id)
            if u.login is not None:
                button_text += " (@%s)" % u.login
            kb.row(telebot.types.InlineKeyboardButton(text=button_text, callback_data="admin:user_info:%d" % u.core_id))

        nav = []
        if page > 0 or not is_last_page:
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if page <= 0 else "⬅️",
                callback_data="//" if page <= 0 else "admin:list_users:%d" % (page - 1),
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="Стр. %d" % (page + 1),
                callback_data="//"
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if is_last_page else "➡️",
                callback_data="//" if is_last_page else "admin:list_users:%d" % (page + 1),
            ))
            kb.row(*nav)

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="main"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="admin:list_users:%d" % page))

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_admin_user(self, data, user):
        about_user_core = data["handled_user"]
        try:
            about_user = User.get(User.core_id == about_user_core.id)
        except KeyError:
            print("ERROR [Bot]: No user with id = %d" % about_user_core.id)
            return

        if about_user.login is None:
            login = self.bot.get_chat(about_user).login
            if login is not None:
                about_user.login = login

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        if about_user_core.banned:
            kb.row(telebot.types.InlineKeyboardButton(text="Разбанить",
                                                      callback_data="admin:unban_user:%d" % about_user.core_id))
        else:
            kb.row(telebot.types.InlineKeyboardButton(text="Забанить нафиг",
                                                      callback_data="admin:ban_user:%d" % about_user.core_id))
        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK,
                                                  callback_data="admin:list_users:0"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH,
                                                  callback_data="admin:user_info:%d" % about_user.core_id))

        message_text = "Информация о пользователе\n" \
                       "%d" % about_user.tg_id
        if about_user.login is not None:
            message_text += " (@%s)\n" % about_user.login
        message_text += "\n"
        if data['req_cnt'] > 0:
            message_text = "\nПоследние запросы:\n"
            for r in data['requests']:
                message_text += r.text + "\n"

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

# BRAIN LISTENER #####
    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)

            try:
                user = User.get(User.core_id == task["user_id"])
            except peewee.DoesNotExist:
                user = None

            print("DEBUG [Bot]: Task from core: %s" % str(task))

            if "action" in task and user is not None:
                action = task["action"]
                handlers = {
                    "user_message": self.listened_user_message,
                    "access_denied": self.listened_access_denied,
                    "error": self.listened_user_message,
                }

                if action in handlers:
                    handlers[action](task, user)
                else:
                    print("ERROR [Bot]: Unknown action: " + str(task["action"]))
            elif "request_id" in task:
                try:
                    new_task = self.generators[task["request_id"]].send(task)
                    if new_task is not None:
                        new_task["request_id"] = task["request_id"]
                        new_task["user_id"] = getattr(user, "core_id", None)
                        self.output_queue.put(new_task)
                except StopIteration:
                    self.generators[task["request_id"]] = None
                    pass
            else:
                print("ERROR [Bot]: Bad task from core: " + str(task))

            print("DEBUG [Bot]: Task done: %s" % str(task))
            self.input_queue.task_done()

    def listened_user_message(self, task, user):
        self.bot.send_message(user.tg_id, task["message"])

    def listened_access_denied(self, _, user):
        self.bot.send_message(user.tg_id, "К вашему сожалению, вы были заблокированы :/")

        if user.tg_id not in self.bamboozled_users:
            self.bamboozled_users.append(user.tg_id)
            self.bot.send_sticker(user.tg_id, data="CAADAgADiwgAArcKFwABQMmDfPtchVkC")


# UTILITY FUNCTIONS #####
    def broadcast_to_all_users(self, message):
        pass
        # if message.from_user.id in superusers:
        #     text = message.text.lstrip("/broadcast ")
        #     if len(text) > 0:
        #         for user in self.user_info:
        #             self.bot.send_message(user, text)
        # else:
        #     self.bot.send_message(message.from_user.id, "You have no power here")

    def get_user_info(self, message):
        pass
        # if message.from_user.id in superusers:
        #     try:
        #         num = int(message.text.lstrip("/get_info "))
        #     except ValueError:
        #         self.bot.send_message(message.from_user.id, "bad id")
        #     else:
        #         if num in self.user_info:
        #             self.bot.send_message(message.from_user.id, str(self.bot.get_chat(num).__dict__))
        #         else:
        #             self.bot.send_message(message.from_user.id, "no such user")
        # else:
        #     self.bot.send_message(message.from_user.id, "You have no power here")

# COMMANDS #####
    def stop_playing(self, _message, _user):
        yield {"action": "stop_playing"}

    def skip_song(self, _message, _user):
        yield {"action": "skip_song"}

    def start_handler(self, message, user):
        self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
        response = yield {"action": "get_status"}
        self.send_menu_main(response, user)

    def init_user(self, data, _null):
        response = yield {
            "action": "init_user",
            "frontend_user": data.from_user,
        }

        user_info = response["frontend_user"]
        user_id = response["user_id"]
        user = User.create(
            tg_id=user_info.id,
            core_id=user_id,
            login=user_info.username,
            first_name=user_info.first_name,
            last_name=user_info.last_name,
        )

        self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
        response = yield {"action": "get_status"}
        self.send_menu_main(response, user)

# USER MESSAGES HANDLERS #####

    def file_handler(self, message):
        self.bot.send_message(message.from_user.id, "Такое не принимаем. (И вам не советуем)")

    def sticker_handler(self, message):
        self.bot.send_sticker(message.from_user.id, data="CAADAgADLwMAApAAAVAg-c0RjgqiVyMC")