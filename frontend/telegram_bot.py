import telebot
import threading
from queue import Queue
import re
import os
import peewee
from time import sleep
import time

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


db.connect()


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".") and f != "bans"]


def make_caption(number, word_forms):
    if 10 < number % 100 < 20:
        return word_forms[0] + word_forms[5]
    for i in range(1, 5):
        if number % 10 == i:
            return word_forms[0] + word_forms[i]
    return word_forms[0] + word_forms[5]


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

# INIT #####
    def bot_init(self):
        while True:
            try:
                print("INFO [Bot]: Loading bot")
                self.bot.polling(none_stop=True)
            except Exception as e:
                print("ERROR [Bot]: CONNECTION PROBLEM")
                print(e)
                sleep(5)

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(commands=['broadcast'])(self.broadcast_to_all_users)
        self.bot.message_handler(commands=['get_info'])(self.get_user_info)
        self.bot.message_handler(commands=['stop_playing', 'stop'])(self.stop_playing)
        self.bot.message_handler(commands=['skip_song', 'skip'])(self.skip_song)
        self.bot.message_handler(commands=['/'])(lambda x: True)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        self.bot.message_handler(content_types=['audio'])(self.audio_handler)

    def init_callbacks(self):
        self.bot.callback_query_handler(func=lambda x: x.data[0:2] == "//")(lambda x: True)
        self.bot.callback_query_handler(func=lambda x: True)(self.callback_query_handler)

        self.bot.inline_handler(func=lambda x: True)(self.search)
        self.bot.chosen_inline_handler(func=lambda x: True)(self.search_select)

    def cleanup(self):
        pass


#######################
# TG CALLBACK HANDLERS
    def callback_query_handler(self, data):

        # TODO: Delete old menu only when ready to display a new one
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("ERROR [Bot]: delete_message exception: " + str(e))
            return

        user = self.init_user(data.from_user)
        if user is None:
            return

        path = data.data.split(":")
        if len(path) == 0:
            print("ERROR [Bot]: Bad menu path: " + str(path))
            return

        self.output_queue.put({
            "action": "menu_event",
            "path": path,
            "user_id": user.core_id,
        })

    def search(self, data):
        user = self.init_user(data.from_user)
        if user is None:
            return

        self.output_queue.put({
            "action": "search",
            "qid": data.id,
            "query": data.query.lstrip(),
            "user_id": user.core_id
        })

    def search_select(self, data):
        user = self.init_user(data.from_user)
        if user is None:
            return

        downloader, result_id = data.result_id.split(" ")
        reply = self.bot.send_message(data.from_user.id, "Запрос обрабатывается...")

        self.output_queue.put({
            "action": "download",
            "user_id": user.core_id,
            "downloader": downloader,
            "result_id": result_id,
            "message_id": reply.message_id,
            "chat_id": reply.chat.id,
        })


# MENU RELATED #####
    def listened_menu(self, task, user):
        menu = task["entry"]

        handlers = {
            "main": self.send_menu_main,
            "queue": self.send_menu_queue,
            "song_details": self.send_menu_song,
            "admin_list_users": self.send_menu_admin_list_users,
            "admin_user": self.send_menu_admin_user,
        }

        if menu in handlers:
            handlers[menu](task, user)
        else:
            print("ERROR [Bot]: Unknown menu: " + str(menu))

    def send_menu_main(self, task, user):
        superuser = task["superuser"]
        queue_len = task["queue_len"]
        now_playing = task["now_playing"]

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        message_text = ""

        if now_playing is not None:
            title = now_playing["title"]

            if now_playing["user_id"] is not None:
                track_author = User.get(id=now_playing["user_id"])
                author_str = track_author.first_name + " " + track_author.last_name
            else:
                author_str = "Студсовет"

            duration = now_playing["duration"]
            str_duration = "{:d}:{:02d}".format(*list(divmod(duration, 60)))

            played_time = int(time.time() - now_playing["start_time"])
            str_played = "{:d}:{:02d}".format(*list(divmod(played_time, 60)))

            message_text += "🔊 \[%s / %s]`    `👤 %s\n" % (str_played, str_duration, author_str) + \
                            "__%s__\n\n" % title
            if superuser:
                kb.row(
                    telebot.types.InlineKeyboardButton(text="⏹ Остановить", callback_data="admin:stop_playing"),
                    telebot.types.InlineKeyboardButton(text="▶️ Переключить", callback_data="admin:skip_song"),
                )
            queue_len_str = "%d %s" % (queue_len, make_caption(queue_len, ['трек', '', 'а', 'а', 'а', 'ов']))
            kb.row(telebot.types.InlineKeyboardButton(text="📂 Очередь: %s" % queue_len_str,
                                                      callback_data="queue:0"))
        else:
            message_text += "🔇 Пока ничего не играет. Будь первым!"
            if superuser:
                kb.row(
                    telebot.types.InlineKeyboardButton(text="▶️ Запустить", callback_data="admin:skip_song"),
                )
                kb.row(telebot.types.InlineKeyboardButton(text="📂 Очередь", callback_data="queue:0"))

        next_in_queue = task["next_in_queue"]

        if superuser and next_in_queue is not None:
            if next_in_queue.user is not None:
                track_author = User.get(id=next_in_queue.user)
                author_str = track_author.first_name + " " + track_author.last_name
            else:
                author_str = "\[Резерв]"

            str_duration = "{:d}:{:02d}".format(*list(divmod(next_in_queue.duration, 60)))
            message_text += "Следующая в очереди:\n" + \
                            "⏱ %s`    `👤 %s\n" % (str_duration, author_str) + \
                            "%s\n" % next_in_queue.title

        if superuser:
            kb.row(telebot.types.InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:list_users:0"))

        kb.row(telebot.types.InlineKeyboardButton(text="🔍 Поиск музыки", switch_inline_query_current_chat=""))
        kb.row(telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="main"))
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb, parse_mode="Markdown")

    def send_menu_queue(self, task, user):
        page = task["page"]
        songs_list = task["songs_list"]
        is_last_page = task["is_last_page"]

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
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_song(self, task, user):
        superuser = task['superuser']
        sid = task["number"]
        duration = task["duration"]
        rating = task["rating"]
        position = task["position"]
        page = task["page"]
        title = task["title"]

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
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_admin_list_users(self, task, user):
        page = task["page"]
        users_list = task["users_list"]
        users_cnt = task["users_cnt"]
        is_last_page = task["is_last_page"]

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

        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_admin_user(self, task, user):
        about_user_core = task["about_user"]
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
        if task['req_cnt'] > 0:
            message_text = "\nПоследние запросы:\n"
            for r in task['requests']:
                message_text += r.text + "\n"

        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)


# BRAIN LISTENER #####
    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            if task["user_id"] == "System":
                self.input_queue.task_done()
                continue

            try:
                user = User.get(User.core_id == task["user_id"])
            except peewee.DoesNotExist:
                user = None

            if user is None and task["action"] != "user_init_done":
                print("ERROR [Bot]: Task for unknown user: %d" % task["user_id"])
                continue

            if task["action"] == "user_init_done":
                print("INFO [Bot]: User init done: %s" % str(task))
                self.listened_user_init_done(task)
                continue

            print("DEBUG [Bot]: Task from core: %s" % str(task))

            action = task["action"]
            handlers = {
                "user_message": self.listened_user_message,
                "edit_user_message": self.listened_edit_user_message,
                "no_dl_handler": self.listened_no_dl_handler,
                "search_results": self.listened_search_results,
                "access_denied": self.listened_access_denied,
                "menu": self.listened_menu,
            }

            if action in handlers:
                handlers[action](task, user)
            else:
                print("ERROR [Bot]: Unknown action: " + str(task))
            self.input_queue.task_done()

# BRAIN LISTENERS  #####
    def listened_user_init_done(self, task):
        user_info = task["frontend_user"]
        user_id = task["user_id"]
        user = User.create(
            tg_id=user_info.id,
            core_id=user_id,
            login=user_info.username,
            first_name=user_info.first_name,
            last_name=user_info.last_name,
        )

        self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
        self.output_queue.put({
            "action": "menu_event",
            "path": ["main"],
            "user_id": user.core_id,
        })

    def listened_user_message(self, task, user):
        self.bot.send_message(user.tg_id, task["message"], reply_markup=telebot.types.ReplyKeyboardRemove())

    def listened_edit_user_message(self, task, _):
        self.bot.edit_message_text(task["new_text"], task["chat_id"], task["message_id"])

    def listened_search_results(self, task, _):
        results = []
        for song in task["results"]:
            results.append(telebot.types.InlineQueryResultArticle(
                id=song['downloader'] + " " + song['id'],
                title=song['artist'],
                description=song['title'] + " {:d}:{:02d}".format(*list(divmod(song["duration"], 60))),
                input_message_content=telebot.types.InputTextMessageContent(
                    "// " + song['artist'] + " - " + song['title']
                ),
            ))

        self.bot.answer_inline_query(task["qid"], results)

    def listened_no_dl_handler(self, task, user):
        text = task["text"]

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(
            text="🔍 " + text,
            switch_inline_query_current_chat=text,
        ))
        if "chat_id" in task and "message_id" in task:
            self.bot.edit_message_text("Запрос не распознан. Нажмите на кнопку ниже, чтобы включить поиск", task["chat_id"], task["message_id"])
            self.bot.edit_message_reply_markup(task["chat_id"], task["message_id"], reply_markup=kb)
        else:
            self.bot.send_message(user.tg_id, "Запрос не распознан. Нажмите на кнопку ниже, чтобы включить поиск",
                                  reply_markup=kb)

    def listened_access_denied(self, _, user):
        self.bot.send_message(user.tg_id, "К вашему сожалению, вы были заблокированы :/")


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
    def stop_playing(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        self.output_queue.put({
            "action": "menu_event",
            "path": "admin:stop_playing",
            "user_id": user.core_id,
        })

    def skip_song(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        self.output_queue.put({
            "action": "menu_event",
            "path": "admin:skip_song",
            "user_id": user.core_id,
        })

    def start_handler(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
        self.output_queue.put({
            "action": "menu_event",
            "path": ["main"],
            "user_id": user.core_id,
        })

    def init_user(self, from_user):
        try:
            user = User.get(User.tg_id == from_user.id)
            return user
        except peewee.DoesNotExist:
            self.output_queue.put({
                "action": "init_user",
                "frontend_user": from_user,
            })
            return None

# USER MESSAGES HANDLERS #####
    def text_message_handler(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        text = message.text

        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")
        request = {
            "action": "download",
            "user_id": user.core_id,
            "text": text,
            "message_id": reply.message_id,
            "chat_id": reply.chat.id,
        }
        self.output_queue.put(request)

    def audio_handler(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        # if message.audio.mime_type == "audio/mpeg3":
        file_info = self.bot.get_file(message.audio.file_id)

        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")
        self.output_queue.put({
            "action": "download",
            "user_id": user.core_id,
            "file": message.audio.file_id,
            "duration": message.audio.duration,
            "file_size": message.audio.file_size,
            "file_info": file_info,
            "artist": message.audio.performer or "",
            "title": message.audio.title or "",
            "message_id": reply.message_id,
            "chat_id": reply.chat.id,
        })
        # else:
        #     self.bot.send_message(message.from_user.id, "Unsupported audio format... For now I accept only mp3 :(")
