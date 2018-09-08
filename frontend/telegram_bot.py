import telebot
import threading
from queue import Queue
import re
import os
import json
from time import sleep

from .private_config import token
from .config import cacheDir, superusers, DEBUG_USER

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
STR_REFRESH = "🔄 Обновить 🔄"


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".") and f != "bans"]


class TgFrontend:

    def __init__(self):
        self.bot = telebot.TeleBot(token)
        self.botThread = threading.Thread(daemon=True, target=self.bot_init)
        self.botThread.start()
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.brainThread = threading.Thread(daemon=True, target=self.brain_listener)
        self.brainThread.start()
        # USER STATES:
        # 0 - basic
        # 1 - asked for confirmation
        # 2 - waiting for response
        self.init_handlers()
        self.init_callbacks()

# INIT #####
    def bot_init(self):
        while True:
            try:
                print("Loading bot")
                self.bot.polling(none_stop=True)
            except Exception as e:
                print("SEEMS LIKE INTERNET IS BROKEN")
                print(e)
                sleep(5)

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(commands=['broadcast'])(self.broadcast_to_all_users)
        self.bot.message_handler(commands=['get_info'])(self.get_user_info)
        self.bot.message_handler(commands=['ms'])(self.manual_start)
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
        cache_path = os.path.join(os.getcwd(), cacheDir)
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)
        print("TG - Users saved.")


#######################
# TG CALLBACK HANDLERS
    def callback_query_handler(self, data):

        # TODO: Delete old menu only when ready to display a new one
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("ERROR [Bot]: delete_message exception: " + str(e))
            return

        self.init_user(data.from_user.id, data.from_user.username)

        path = data.data.split(":")
        if len(path) == 0:
            print("ERROR [Bot]: Bad menu path: " + str(path))
            return

        self.output_queue.put({
            "action": "menu_event",
            "path": path,
            "user": data.from_user.id,
        })

    def menu_main(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        self.output_queue.put({
            "action": "menu",
            "entry": "main",
            "user": data.from_user.id
        })

    def vote_callback(self, data):
        try:
            self.bot.edit_message_text("Ваш голос учтен.", chat_id=data.from_user.id, message_id=data.message.message_id)
        except Exception:
            return
        if data.data[4] == "+":
            action = "vote_up"
        else:
            action = "vote_down"
        self.output_queue.put({
            "action": action,
            "sid": int(data.data[5:]),
            "user": data.from_user.id
        })

    def search(self, data):
        self.output_queue.put({
            "action": "search",
            "qid": data.id,
            "query": data.query.lstrip(),
            "user": data.from_user.id
        })

    def search_select(self, data):
        downloader, result_id = data.result_id.split(" ")

        reply = self.bot.send_message(data.from_user.id, "Запрос обрабатывается...")

        self.output_queue.put({
            "action": "download",
            "user": data.from_user.id,
            "downloader": downloader,
            "result_id": result_id,
            "message_id": reply.message_id,
            "chat_id": reply.chat.id,
        })


# MENU RELATED #####
    def listened_menu(self, task):
        menu = task["entry"]

        handlers = {
            "main": self.send_menu_main,
            "queue": self.send_menu_queue,
            "song_details": self.send_menu_song,
            "admin_list_users": self.send_menu_admin_list_users,
            "admin_user": self.send_menu_admin_user,
        }

        if menu in handlers:
            handlers[menu](task)
        else:
            print("ERROR [Bot]: Unknown menu: " + str(menu))

    def send_menu_main(self, task):
        user = task["user"]
        superuser = task["superuser"]
        queue_len = task["queue_len"]
        now_playing = task["now_playing"]

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        if now_playing is not None:
            message_text = "Сейчас играет: {:s}\nПесен в очереди: {:d}".format(now_playing, queue_len)
            if superuser:
                kb.row(
                    telebot.types.InlineKeyboardButton(text="⏹ Остановить", callback_data="admin:stop_playing"),
                    telebot.types.InlineKeyboardButton(text="⏩ Пропустить", callback_data="admin:skip_song"),
                )
            kb.row(telebot.types.InlineKeyboardButton(text="📂 Очередь", callback_data="queue:0"))
        else:
            message_text = "Ничего не играет пока, будь первым!"

        if superuser:
            kb.row(telebot.types.InlineKeyboardButton(text="Пользователи", callback_data="admin:list_users:0"))

        kb.row(telebot.types.InlineKeyboardButton(text="🔍 Поиск музыки", switch_inline_query_current_chat=""))
        kb.row(telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="main"))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_queue(self, task):
        user = task["user"]
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
        if page > 0:
            nav.append(telebot.types.InlineKeyboardButton(text="⬅️", callback_data="queue:%d" % (page - 1)))
        if page > 0 or not is_last_page:
            nav.append(telebot.types.InlineKeyboardButton(text="Страница: %d" % (page + 1), callback_data="//"))
        if not is_last_page:
            nav.append(telebot.types.InlineKeyboardButton(text="➡️", callback_data="queue:%d" % (page + 1)))
        kb.row(*nav)

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="main"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="queue:%d" % page))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_song(self, task):
        user = task["user"]
        superuser = task['superuser']
        sid = task["number"]
        duration = task["duration"]
        rating = task["rating"]
        position = task["position"]
        title = task["title"]

        str_duration = "{:d}:{:02d}".format(*list(divmod(duration, 60)))
        base_str = "Песня: {}\nПродолжительность: {}\nРейтинг: {:d}\nМесто в очереди: {:d}"
        message_text = base_str.format(title, str_duration, rating, position)
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(text="👍", callback_data="vote:up:%s" % sid),
               telebot.types.InlineKeyboardButton(text="👎", callback_data="vote:down:%s" % sid))

        if superuser:
            kb.row(telebot.types.InlineKeyboardButton(text="Удалить", callback_data="admin:delete:%s" % sid))

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="queue:%d" % position),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="song:%s" % sid))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_admin_list_users(self, task):
        print(str(task))
        user = task["user"]
        page = task["page"]
        users_list = task["users_list"]
        users_cnt = task["users_cnt"]
        is_last_page = task["is_last_page"]

        if users_cnt == 0:
            message_text = "Нет ни одного пользователя"
        else:
            message_text = "Количество пользователей: %d" % users_cnt

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        for u in users_list:
            button_text = str(u.id)
            if u.username is not None:
                button_text += " (@%s)" % u.username
            kb.row(telebot.types.InlineKeyboardButton(text=button_text, callback_data="admin:user_info:%d" % u.id))

        nav = []
        if page > 0:
            nav.append(telebot.types.InlineKeyboardButton(text="⬅️", callback_data="admin:list_users:%d" % (page - 1)))
        if page > 0 or not is_last_page:
            nav.append(telebot.types.InlineKeyboardButton(text="Страница: %d" % (page + 1), callback_data="//"))
        if not is_last_page:
            nav.append(telebot.types.InlineKeyboardButton(text="➡️", callback_data="admin:list_users:%d" % (page + 1)))
        kb.row(*nav)

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="main"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="admin:list_users:%d" % page))

        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_admin_user(self, task):
        user = task["user"]
        about_user = task["about_user"]

        if about_user.username is None:
            username = self.bot.get_chat(about_user).username
            if username is not None:
                about_user.username = username

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        if about_user.banned:
            kb.row(telebot.types.InlineKeyboardButton(text="Разбанить", callback_data="admin:unban_user:%d" % about_user.id))
        else:
            kb.row(telebot.types.InlineKeyboardButton(text="Забанить нафиг", callback_data="admin:ban_user:%d" % about_user.id))
        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="admin:list_users:0"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="admin:user_info:%d" % about_user.id))

        message_text = "Информация о пользователе\n" \
                       "%d" % about_user.id
        if about_user.username is not None:
            message_text += "(@%s)\n" % about_user.username
        message_text += "\n"
        # if len(user_info['history']) > 0:
        #     history = "\n".join(user_info['history'])
        # else:
        #     history = "Ничего не заказывал"
        # message_text = "Id: {:d}\n{:s}История заказов:\n{:s}".format(about_user, username, history)
        self.bot.send_message(user, message_text, reply_markup=kb)


# BRAIN LISTENER #####
    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            if task["user"] == "System":
                self.input_queue.task_done()
                continue

            action = task["action"]

            if action == "user_message":
                self.listened_user_message(task)
            elif action == "edit_user_message":
                self.listened_edit_user_message(task)
            elif action == "confirmation_done":
                self.listened_confirmation_done(task)
            elif action == "no_dl_handler":
                self.listened_no_dl_handler(task)
            elif action == "search_results":
                self.listened_search_results(task)
            elif action == "access_denied":
                self.listened_access_denied(task)
            elif action == "menu":
                self.listened_menu(task)
            else:
                self.bot.send_message(DEBUG_USER, "DEBUG:\n" + str(task),
                                      reply_markup=telebot.types.ReplyKeyboardRemove())
            self.input_queue.task_done()

# BRAIN LISTENERS  #####
    def listened_user_message(self, task):
        self.bot.send_message(task["user"], task["message"], reply_markup=telebot.types.ReplyKeyboardRemove())

    def listened_edit_user_message(self, task):
        self.bot.edit_message_text(task["new_text"], task["chat_id"], task["message_id"])

    def listened_confirmation_done(self, task):
        pass

    def listened_search_results(self, task):
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

    def listened_no_dl_handler(self, task):
        user = task["user"]
        text = task["text"]

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(
            text="🔍 " + text,
            switch_inline_query_current_chat=text,
        ))
        if "chat_id" in task and "message_id" in task:
            self.bot.edit_message_text("Запрос неясен. Попробуем поискать?", task["chat_id"], task["message_id"])
            self.bot.edit_message_reply_markup(task["chat_id"], task["message_id"], reply_markup=kb)
        else:
            self.bot.send_message(user, "Запрос неясен. Попробуем поискать?", reply_markup=kb)

    def listened_access_denied(self, task):
        user = task["user"]
        self.bot.send_message(user, "К вашему сожалению, вы были заблокированы :/")


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
    def manual_start(self, message):
        if message.from_user.id in superusers:
            self.output_queue.put({
                "action": "manual_start",
                "user": message.from_user.id
            })

    def stop_playing(self, message):
        self.output_queue.put({
            "action": "stop_playing",
            "user": message.from_user.id
        })

    def skip_song(self, message):
        self.output_queue.put({
            "action": "skip_song",
            "user": message.from_user.id
        })

    def start_handler(self, message):
        self.init_user(message.from_user.id, message.from_user.username)
        self.bot.send_message(message.from_user.id, help_message, disable_web_page_preview=True)
        self.output_queue.put({
            "action": "menu_event",
            "path": ["main"],
            "user": message.from_user.id,
        })

    def init_user(self, uid, username):
        self.output_queue.put({
            "action": "init_user",
            "uid": uid,
            "username": username,
        })

# USER MESSAGES HANDLERS #####
    def text_message_handler(self, message):
        self.init_user(message.from_user.id, message.from_user.username)

        user = message.from_user.id
        text = message.text

        reply = self.bot.send_message(user, "Запрос обрабатывается...")
        request = {
            "action": "download",
            "user": user,
            "text": text,
            "message_id": reply.message_id,
            "chat_id": reply.chat.id,
        }
        self.output_queue.put(request)

    def audio_handler(self, message):
        self.init_user(message.from_user.id, message.from_user.username)

        # if message.audio.mime_type == "audio/mpeg3":
        user = message.from_user.id
        file_info = self.bot.get_file(message.audio.file_id)

        reply = self.bot.send_message(user, "Запрос обрабатывается...")
        self.output_queue.put({
            "action": "download",
            "user": user,
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
            # self.bot.send_message(message.from_user.id, "Unsupported audio format... For now I accept only mp3 :(")
