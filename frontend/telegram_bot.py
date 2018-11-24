import telebot
import threading
import re
import peewee
import time
import math
import traceback

from .jinja_env import env
import asyncio

from .private_config import token

from brain.DJ_Brain import UserBanned, UserRequestQuotaReached, DownloadFailed, PermissionDenied
from downloader.exceptions import NotAccepted


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

        self.core = None
        self.bot = None

        self.bamboozled_users = []

        self.songs_per_page = 10
        self.users_per_page = 10

    def bind_core(self, core):
        self.core = core

        self.bot = telebot.TeleBot(token)
        self.bot_init()

# INIT #####
    def bot_init(self):
        print("INFO [Bot %s]: Starting polling..." % threading.get_ident())
        self.core.loop.create_task(self.bot_polling())

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

    def updates_handler(self, updates):
        for update in updates:
            if update.update_id > self.last_update_id:
                self.last_update_id = update.update_id

            if update.message:
                asyncio.run_coroutine_threadsafe(self.message_handler(update.message), self.core.loop)
            elif update.inline_query:
                asyncio.run_coroutine_threadsafe(self.inline_query_handler(update.inline_query), self.core.loop)
            elif update.chosen_inline_result:
                asyncio.run_coroutine_threadsafe(self.chosen_inline_result_handler(update.chosen_inline_result), self.core.loop)
            elif update.callback_query:
                asyncio.run_coroutine_threadsafe(self.callback_query_handler(update.callback_query), self.core.loop)

        asyncio.run_coroutine_threadsafe(self.bot_polling(), self.core.loop)

    def cleanup(self):
        pass

    async def message_handler(self, message):
        try:
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
        except Exception as e:
            traceback.print_exc()

    async def inline_query_handler(self, inline_query):
        try:
            await self.tg_handler(inline_query, self.search)
        except Exception as e:
            traceback.print_exc()

    async def chosen_inline_result_handler(self, chosen_inline_result):
        try:
            await self.tg_handler(chosen_inline_result, self.search_select)
        except Exception as e:
            traceback.print_exc()

    async def callback_query_handler(self, callback_query):
        try:
            await self.tg_handler(callback_query, self.menu_handler)
        except Exception as e:
            traceback.print_exc()

    async def menu_handler(self, data, user):
        if data.data[0:2] == "//":
            return

        user.menu_message_id = data.message.message_id
        user.menu_chat_id = data.message.chat.id
        user.save()

        path = data.data.split(":")
        if len(path) == 0:
            print("ERROR [Bot]: Bad menu path: " + str(path))
            return

        if path[0] == "main":
            self.send_menu_main(user)

        elif path[0] == "queue":
            offset = int(path[1]) if len(path) >= 2 else 0
            self.send_menu_queue(user, offset)

        elif path[0] == "song":
            song_id = int(path[1])
            self.send_menu_song(user, song_id)

        elif path[0] == "vote":
            sign = path[1]
            song_id = int(path[2])
            self.core.vote_song(user.core_id, sign, song_id)
            self.send_menu_song(user, song_id)

        elif path[0] == "admin" and path[1] == "skip_song":
            self.core.switch_track(user.core_id)
            # TODO: await track switch
            self.send_menu_main(user)

        elif path[0] == "admin" and path[1] == "stop_playing":
            self.core.stop_playback(user.core_id)
            self.send_menu_main(user)

        elif path[0] == "admin" and path[1] == "delete":
            song_id = int(path[2])
            position = self.core.delete_track(user.core_id, song_id)
            offset = ((position - 1) // self.songs_per_page) * self.songs_per_page
            self.send_menu_queue(user, offset)

        elif path[0] == "admin" and path[1] == "list_users":
            offset = int(path[2]) if len(path) >= 2 else 0
            self.send_menu_admin_list_users(user, offset)

        elif path[0] == "admin" and path[1] == "user_info":
            handled_user_id = int(path[2])
            self.send_menu_admin_user(user, handled_user_id)

        elif path[0] == "admin" and path[1] == "ban_user":
            handled_user_id = int(path[2])
            self.core.ban_user(user.core_id, handled_user_id)
            self.send_menu_admin_user(user, handled_user_id)

        elif path[0] == "admin" and path[1] == "unban_user":
            handled_user_id = int(path[2])
            self.core.unban_user(user.core_id, handled_user_id)
            self.send_menu_admin_user(user, handled_user_id)

        else:
            print("ERROR [Bot]: Unknown menu: " + str(path))

    async def tg_handler(self, data, method):
        user = self.init_user(data.from_user)
        try:
            await method(data, user)
        except UserBanned:
            self._show_blocked_msg(user)
        except PermissionDenied:
            self._show_access_denied(user)

    async def search(self, data, user):
        query = data.query.lstrip()

        def message_callback(test):
            try:
                self.bot.send_message(user.tg_id, test)
            except telebot.apihelper.ApiException:
                pass

        results = await self.core.search_action(user.id, query=query, message_callback=message_callback)
        print("DEBUG [Bot - search]: Response from core: %d results" % len(results))

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

        try:
            song, position = await self.core.download_action(
                user.id,
                result={"downloader": downloader, "id": result_id},
                progress_callback=progress_callback
            )
            self.bot.edit_message_text(
                "Песня в очереди. Позиция: %d\n%s" % (position, song.full_title()),
                reply.chat.id, reply.message_id
            )
        except NotAccepted:
            self.bot.send_message(user.tg_id, "🚫 Внутренняя ошибка: ни один загрузчик не принял запрос")
        except DownloadFailed:
            self.bot.send_message(user.tg_id, "🚫 Не удалось загрузить песню")
        except UserRequestQuotaReached:
            self._show_quota_reached_msg(user)

    async def command(self, message, user):

        handlers = {
           'start': self.start_handler,
           'broadcast': self.broadcast_to_all_users,
           'get_info': self.get_user_info,
           'stop_playing': self.stop_playing,
           'stop': self.stop_playing,
           'skip_song': self.skip_song,
           'skip': self.skip_song,
        }

        for e in message.entities:
            if e.type != "bot_command":
                continue

            command = message.text[e.offset + 1:e.offset + e.length]

            if command not in handlers:
                print("WARNING [Bot]: Unknown command: %s" % command)
                return

            handlers[command](message)

    async def download(self, message, user):
        print("DEBUG [Bot]: Download: " + str(message.text))
        text = message.text

        if text[0:2] == "//":
            return

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

        try:
            song, position = await self.core.download_action(user.id, text=text, progress_callback=progress_callback)
            self.bot.edit_message_text(
                "Песня в очереди. Позиция: %d\n%s" % (position, song.full_title()),
                reply.chat.id, reply.message_id
            )
        except NotAccepted:
            self._suggest_search(text, reply.chat.id, reply.message_id)
        except DownloadFailed:
            self.bot.send_message(user.tg_id, "🚫 Не удалось загрузить песню")
        except UserRequestQuotaReached:
            self._show_quota_reached_msg(user)

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

        try:
            song, position = await self.core.download_action(user.id, file=file, progress_callback=progress_callback)
            self.bot.edit_message_text(
                "Песня в очереди. Позиция: %d\n%s" % (position, song.full_title()),
                reply.chat.id, reply.message_id
            )
        except NotAccepted:
            self.bot.send_message(user.tg_id, "🚫 Внутренняя ошибка: ни один загрузчик не принял запрос")
        except DownloadFailed:
            self.bot.send_message(user.tg_id, "🚫 Не удалось загрузить песню")
        except UserRequestQuotaReached:
            self._show_quota_reached_msg(user)

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

    def send_menu_main(self, user):
        menu_template = """
            {% if superuser %}
                {% if current_song is not none %}
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
            {% if current_song is not none %}
                🔊 [{{ current_song_progress | format_duration }} / {{ current_song.duration | format_duration }}]    👤 {{ current_user.name if current_user else "Студсовет" }}
                {{ current_song.full_title() }}\n
            {% endif %}
            {% if superuser and next_song is not none %}
                Следующий трек:
                ⏱ {{ next_song.duration | format_duration }}    👤 {{ next_user.name if next_user else "Студсовет" }}
                {{ next_song.full_title() }}
            {% endif %}
        """

        state = self.core.get_state(user.core_id)

        template = env.from_string(menu_template)
        rendered = template.render(**state)
        kb = self.build_markup(rendered)

        template = env.from_string('\n'.join([l.strip() for l in msg_template.splitlines(False)]))
        message_text = template.render(**state)

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_queue(self, user, offset):
        data = self.core.get_queue(user.core_id, offset, self.songs_per_page)
        songs = data["list"]
        songs_cnt = data["cnt"]

        if songs_cnt == 0:
            message_text = "Очередь воспроизведения пуста"
        else:
            message_text = "Очередь воспроизведения\nПесен в очереди: %d" % songs_cnt

        kb = telebot.types.InlineKeyboardMarkup(row_width=3)
        for song in songs:
            kb.row(telebot.types.InlineKeyboardButton(text=song.full_title(), callback_data="song:%d" % song.id))

        page = math.ceil(offset / self.songs_per_page) + 1
        next_offset = offset + self.songs_per_page
        prev_offset = max(offset - self.songs_per_page, 0)

        nav = []
        if prev_offset >= 0 or next_offset < songs_cnt:
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if offset == 0 else "⬅️",
                callback_data="//" if offset == 0 else "queue:%d" % prev_offset,
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="Стр. %d" % page,
                callback_data="//"
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if next_offset >= songs_cnt else "➡️",
                callback_data="//" if next_offset >= songs_cnt else "queue:%d" % next_offset
            ))
            kb.row(*nav)

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="main"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="queue:%d" % offset))

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_song(self, user, song_id):
        data = self.core.get_song_info(user.core_id, song_id)

        superuser = data['superuser']
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)

        song = data["song"]
        if song is None:
            message_text = "🚫 Не удалось загрузить информацию о песне"
            list_offset = 0
        else:
            duration = "{:d}:{:02d}".format(*list(divmod(song.duration, 60)))
            position = data["position"]

            list_offset = ((position - 1) // self.songs_per_page) * self.songs_per_page

            message_text = "🎵 %s\n\nДлительность: %s\nРейтинг: %d\nМесто в очереди: %d" % \
                           (song.full_title(), duration, song.rating, position)

            kb.row(
                telebot.types.InlineKeyboardButton(text="👍", callback_data="vote:up:%s" % song_id),
                telebot.types.InlineKeyboardButton(text="👎", callback_data="vote:down:%s" % song_id),
            )

            if superuser:
                kb.row(
                    telebot.types.InlineKeyboardButton(text="🚫 Удалить 🚫", callback_data="admin:delete:%s" % song_id)
                )

        kb.row(
            telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="queue:%d" % list_offset),
            telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="song:%s" % song_id),
        )

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_admin_list_users(self, user, offset):
        data = self.core.get_users(user.core_id, offset, self.users_per_page)
        users = data["list"]
        users_cnt = data["cnt"]

        if users_cnt == 0:
            message_text = "Нет ни одного пользователя"
        else:
            message_text = "Количество пользователей: %d" % users_cnt

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        for u in users:
            button_text = "#" + str(u.id) + (" - %s" % u.name if u.name else "")
            kb.row(telebot.types.InlineKeyboardButton(text=button_text, callback_data="admin:user_info:%d" % u.id))

        page = math.ceil(offset / self.users_per_page) + 1
        next_offset = offset + self.users_per_page
        prev_offset = max(offset - self.users_per_page, 0)

        nav = []
        if prev_offset >= 0 or next_offset < users_cnt:
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if offset == 0 else "⬅️",
                callback_data="//" if offset == 0 else "admin:list_users:%d" % prev_offset,
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="Стр. %d" % page,
                callback_data="//"
            ))
            nav.append(telebot.types.InlineKeyboardButton(
                text="." if next_offset >= users_cnt else "➡️",
                callback_data="//" if next_offset >= users_cnt else "admin:list_users:%d" % next_offset,
            ))
            kb.row(*nav)

        kb.row(telebot.types.InlineKeyboardButton(text=STR_BACK, callback_data="main"),
               telebot.types.InlineKeyboardButton(text=STR_REFRESH, callback_data="admin:list_users:%d" % offset))

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def send_menu_admin_user(self, user, handled_user_id):
        data = self.core.get_user_info(user.core_id, handled_user_id)

        handled_user = data["info"]

        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(
            telebot.types.InlineKeyboardButton(
                text="Разбанить" if handled_user.banned else "Забанить нафиг",
                callback_data=("admin:unban_user:%d" if handled_user.banned else "admin:ban_user:%d") % handled_user_id,
            )
        )
        kb.row(
            telebot.types.InlineKeyboardButton(
                text=STR_BACK,
                callback_data="admin:list_users:0"
            ),
            telebot.types.InlineKeyboardButton(
                text=STR_REFRESH,
                callback_data="admin:user_info:%d" % handled_user_id
            )
        )

        message_text = "👤 %s\n\n" % handled_user.name

        try:
            about_user_tg = User.get(User.core_id == handled_user.id)
            message_text += "Telegram ID: %d\n" % about_user_tg.tg_id

            if about_user_tg.login is None:
                login = self.bot.get_chat(about_user_tg.tg_id).login
                about_user_tg.login = login

            if about_user_tg.login is not None:
                message_text += "Login: @%s\n" % about_user_tg.login

            message_text += "\n"
        except KeyError:
            pass

        message_text += "Всего запросов: %d\n" % data['total_requests']
        if len(data['last_requests']) > 0:
            message_text += "Последние запросы:\n"
            for r in data['last_requests']:
                message_text += "- " + r.text + "\n"
        message_text += "\n"

        self.remove_old_menu(user)
        self.bot.send_message(user.tg_id, message_text, reply_markup=kb)

    def notify_user(self, message, uid):
        print("DEBUG [Bot]: Trying to notify user#%d" % uid)
        try:
            user = User.get(User.core_id == uid)
        except peewee.DoesNotExist:
            print("WARNING [Bot]: Trying to notify unexistent user#%d" % uid)
            return
        self._show_status(message, user)

    def _show_status(self, message, user):
        self.bot.send_message(user.tg_id, message)

    def _show_error(self, message, user):
        self.bot.send_message(user.tg_id, message)

    def _show_blocked_msg(self, user):
        self.bot.send_message(user.tg_id, "К вашему сожалению, вы были заблокированы :/")

        if user.tg_id not in self.bamboozled_users:
            self.bamboozled_users.append(user.tg_id)
            self.bot.send_sticker(user.tg_id, data="CAADAgADiwgAArcKFwABQMmDfPtchVkC")

    def _show_quota_reached_msg(self, user):
        self.bot.send_message(user.tg_id, "🛑 Превышена квота на количество запросов. Попробуйте позже.")

    def _show_access_denied(self, user):
        self.bot.send_message(user.tg_id, "❌ Доступ запрещён")

    def _suggest_search(self, text, chat_id, message_id):
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
        self.send_menu_main(user)

    def init_user(self, user_info):
        try:
            user = User.get(User.tg_id == user_info.id)
            if user.first_name != user_info.first_name or user.last_name != user_info.last_name:
                user.first_name = user_info.first_name
                user.last_name = user_info.last_name
                user.save()
                self.core.set_user_name(user.core_id, user.full_name())
                print("DEBUG [Bot]: User name updated: " + user.full_name())
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
            self.core.set_user_name(core_id, user.full_name())
            self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
            return user

# USER MESSAGES HANDLERS #####

    def file_handler(self, message):
        self.bot.send_message(message.from_user.id, "К сожалению, ваш файл не определяется как музыкальный")

    def sticker_handler(self, message):
        self.bot.send_sticker(message.from_user.id, data="CAADAgADLwMAApAAAVAg-c0RjgqiVyMC")
