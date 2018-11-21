import telebot
import threading
import re
import peewee
import time

from .jinja_env import env
import asyncio

from .private_config import token

from brain.DJ_Brain import UserBanned, UserRequestQuotaReached


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
        if self.last_name is None:
            return self.first_name
        else:
            return str(self.first_name) + " " + str(self.last_name)


db.connect()


class TgFrontend:

    def __init__(self):
        self.last_update_id = 0
        self.error_interval = .25
        self.interval = 0
        self.timeout = 20

        self.bot = telebot.TeleBot(token)
        self.botThread = threading.Thread(daemon=True, target=self.bot_init)
        self.botThread.start()

        self.core = None
        self.loop = None

        self.bamboozled_users = []

    def bind_core(self, core):
        self.core = core

# INIT #####
    def bot_init(self):
        print("INFO [Bot %s]: Starting polling..." % threading.get_ident())
        self.loop = asyncio.new_event_loop()
        self.loop.create_task(self.bot_polling())
        self.loop.run_forever()
        print("FATAL [Bot]: Polling loop ended")
        self.loop.close()

    async def bot_polling(self):
        await asyncio.sleep(self.interval)
        threading.Thread(daemon=True, target=self.get_updates).start()

    def get_updates(self):
        try:
            updates = self.bot.get_updates(self.last_update_id + 1, None, self.timeout, )
            self.error_interval = .25
            if len(updates):
                print("DEBUG [Bot]: Updates received: %s" % str(updates))
            self.updates_handler(updates)
        except telebot.apihelper.ApiException as e:
            print("ERROR [Bot]: API Exception")
            print(e)
            print("DEBUG [Bot]: Waiting for %d seconds until retry" % self.error_interval)
            time.sleep(self.error_interval)
            self.error_interval *= 2
        except KeyboardInterrupt:
            self.loop.stop()
            print("INFO [Bot]: KeyboardInterrupt received")

    def updates_handler(self, updates):
        for update in updates:
            if update.update_id > self.last_update_id:
                self.last_update_id = update.update_id

            if update.message:
                asyncio.run_coroutine_threadsafe(self.message_handler(update.message), self.loop)
            elif update.inline_query:
                asyncio.run_coroutine_threadsafe(self.inline_query_handler(update.inline_query), self.loop)
            elif update.chosen_inline_result:
                asyncio.run_coroutine_threadsafe(self.chosen_inline_result_handler(update.chosen_inline_result), self.loop)
            elif update.callback_query:
                asyncio.run_coroutine_threadsafe(self.callback_query_handler(update.callback_query), self.loop)

        asyncio.run_coroutine_threadsafe(self.bot_polling(), self.loop)

    def cleanup(self):
        pass

    async def message_handler(self, message):
        if message.entities and any(e.type == "bot_command" for e in message.entities):
            await self.tg_handler(message, self.command)
        elif message.text:
            await self.tg_handler(message, self.download)
        elif message.audio:
            await self.tg_handler(message, self.add_audio_file)
        elif message.sticker:
            self.sticker_handler(message)
        else:
            self.file_handler(message)

    async def inline_query_handler(self, inline_query):
        await self.tg_handler(inline_query, self.search)

    async def chosen_inline_result_handler(self, chosen_inline_result):
        await self.tg_handler(chosen_inline_result, self.search_select)

    async def callback_query_handler(self, data):
        if data.data[0:2] == "//":
            return

        user = self.init_user(data.from_user)
        if user is None:
            return

        user.menu_message_id = data.message.message_id
        user.menu_chat_id = data.message.chat.id
        user.save()

        path = data.data.split(":")
        if len(path) == 0:
            print("ERROR [Bot]: Bad menu path: " + str(path))
            return

        print("DEBUG [Bot]: Requesting menu data from core: " + str(path))
        data = self.core.menu_action(path, user.core_id)
        print("DEBUG [Bot]: Menu data: " + str(data))

        if path[0] == "main":
            handler = self.send_menu_main
        elif path[0] == "queue":
            handler = self.send_menu_queue
        elif path[0] == "song" or path[0] == "vote":
            handler = self.send_menu_song
        elif path[0] == "admin":
            if path[1] == "skip_song" or path[1] == "stop_playing":
                handler = self.send_menu_main
            elif path[1] == "delete":
                handler = self.send_menu_queue
            elif path[1] == "list_users":
                handler = self.send_menu_admin_list_users
            elif path[1] == "user_info" or path[1] == "ban_user" or path[1] == "unban_user":
                handler = self.send_menu_admin_user
            else:
                print("ERROR [Bot]: Unknown admin menu: " + str(path))
                return
        else:
            print("ERROR [Bot]: Unknown menu: " + str(path))
            return

        handler(data, user)

    async def tg_handler(self, data, method):
        user = self.init_user(data.from_user)
        try:
            await method(data, user)
        except UserBanned:
            self.show_access_denied_msg(user)

    async def search(self, data, user):
        query = data.query.lstrip()

        print("DEBUG [Bot]: Awaiting core: " + query)
        task = await self.core.search_action(user.id, query=query)
        results = task["results"]
        print("DEBUG [Bot]: Response from core: " + str(results))

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

    async def search_select(self, data, user):
        downloader, result_id = data.result_id.split(" ")
        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")

        def progress_callback(progress_msg):
            try:
                self.bot.edit_message_text(progress_msg, reply.chat.id, reply.message_id)
            except telebot.apihelper.ApiException:
                pass

        await self.core.download_action(user.id, result={"downloader": downloader, "id": result_id},
                                        progress_callback=progress_callback)
        self.bot.edit_message_text("Песня добавлена в очередь", reply.chat.id, reply.message_id)

    async def command(self, message, user):

        handlers = {
           'start': self.start_handler,
           'broadcast': self.broadcast_to_all_users,
           'get_info': self.get_user_info,
           'stop_playing': self.stop_playing,
           'stop': self.stop_playing,
           'skip_song': self.skip_song,
           'skip': self.skip_song,
           '/': (lambda x: True),
        }

        for e in message.entities:
            if e.type != "bot_command":
                continue

            command = message.text[e.offset + 1:e.length - 1]

            if command not in handlers:
                print("WARNING [Bot]: Unknown command: %s" % command)
                return

            handlers[command](message)

    async def download(self, message, user):
        print("DEBUG [Bot]: Download: " + str(message.text))
        text = message.text

        if re.search(r'^@\w+ ', text) is not None:
            self.bot.send_message(user.tg_id, "Выберите из интерактивного меню, пожалуйста. "
                                              "Интерактивное меню появляется во время ввода сообщения")
            return

        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")

        def progress_callback(progress_msg):
            try:
                self.bot.edit_message_text(progress_msg, reply.chat.id, reply.message_id)
            except telebot.apihelper.ApiException:
                pass

        await self.core.download_action(user.id, text=text, progress_callback=progress_callback)
        self.bot.edit_message_text("Песня добавлена в очередь", reply.chat.id, reply.message_id)

    async def add_audio_file(self, message, user):
        file_info = self.bot.get_file(message.audio.file_id)

        reply = self.bot.send_message(user.tg_id, "Запрос обрабатывается...")

        def progress_callback(progress_msg):
            try:
                self.bot.edit_message_text(progress_msg, reply.chat.id, reply.message_id)
            except telebot.apihelper.ApiException:
                pass

        file = {
            "id": message.audio.file_id,
            "duration": message.audio.duration,
            "size": message.audio.file_size,
            "info": file_info,
            "artist": message.audio.performer or "",
            "title": message.audio.title or "",
        }

        await self.core.download_action(user.id, file=file, progress_callback=progress_callback)
        self.bot.edit_message_text("Песня добавлена в очередь", reply.chat.id, reply.message_id)

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

    def send_menu_main(self, task, user):
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

        superuser = task["superuser"]
        queue_len = task["queue_len"]

        now_playing = task["now_playing"]
        if now_playing is not None:
            if now_playing["user_id"] is not None:
                track_author = User.get(User.core_id == now_playing["user_id"])
                now_playing["author_name"] = track_author.full_name()
            else:
                now_playing["author_name"] = "Студсовет"

            now_playing["played"] = int(time.time() - now_playing["start_time"])

        next_in_queue = task["next_in_queue"]
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

        self.remove_old_menu(user)
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

        self.remove_old_menu(user)
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

        self.remove_old_menu(user)
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

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def show_status(self, task, user):
        self.bot.send_message(user.tg_id, task["message"])

    def show_error(self, task, user):
        self.bot.send_message(user.tg_id, task["message"])

    def show_access_denied_msg(self, user):
        self.bot.send_message(user.tg_id, "К вашему сожалению, вы были заблокированы :/")

        if user.tg_id not in self.bamboozled_users:
            self.bamboozled_users.append(user.tg_id)
            self.bot.send_sticker(user.tg_id, data="CAADAgADiwgAArcKFwABQMmDfPtchVkC")

    def show_quota_reached_msg(self, user):
        self.bot.send_message(user.tg_id, "Превышен лимит запросов, попробуйте позже")

    def suggest_search(self, text, chat_id, message_id):
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(
            text="🔍 " + text,
            switch_inline_query_current_chat=text,
        ))
        self.bot.edit_message_text("Запрос не распознан. Нажмите на кнопку ниже, чтобы включить поиск",
                                   chat_id, message_id)
        self.bot.edit_message_reply_markup(chat_id, message_id, reply_markup=kb)


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

        self.core.menu_action(["admin", "stop_playing"], user.core_id)

    def skip_song(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        self.core.menu_action(["admin", "skip_song"], user.core_id)

    def start_handler(self, message):
        user = self.init_user(message.from_user)
        if user is None:
            return

        self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
        data = self.core.menu_action(["main"], user.core_id)
        self.send_menu_main(data, user)

    def init_user(self, user_info):
        try:
            user = User.get(User.tg_id == user_info.id)
            return user
        except peewee.DoesNotExist:
            core_id = self.core.user_init_action()
            user = User.create(
                tg_id=user_info.id,
                core_id=core_id,
                login=user_info.username,
                first_name=user_info.first_name,
                last_name=user_info.last_name,
            )
            self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)

# USER MESSAGES HANDLERS #####

    def file_handler(self, message):
        self.bot.send_message(message.from_user.id, "К сожалению, ваш файл не определяется как музыкальный")

    def sticker_handler(self, message):
        self.bot.send_sticker(message.from_user.id, data="CAADAgADLwMAApAAAVAg-c0RjgqiVyMC")
