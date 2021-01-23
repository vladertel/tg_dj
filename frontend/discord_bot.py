# bot.py
import asyncio

import concurrent.futures
from concurrent.futures import CancelledError
import discord
import logging
import traceback

import peewee

class DiscordFrontend:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger('discord.bot')
        self.logger.setLevel(getattr(logging, self.config.get("discord", "verbosity", fallback="warning").upper()))

        self.core = None
        self.bot = None

        self.interval = 0.1

        self.songs_per_page = 7
        self.users_per_page = 7

        self.thread_pool = concurrent.futures.ThreadPoolExecutor()
        self.discord_starting_task = None

        # noinspection PyArgumentList
        # self.mon_tg_updates = Counter('dj_tg_updates', 'Telegram updates counter')

        # noinspection PyArgumentList
        # self.mon_tg_api_errors = Counter('dj_tg_api_errors', 'Telegram API errors')

    def bind_core(self, core):
        self.core = core
        self.bot_init()

    def bot_init(self):
        # discord.opus.load_opus()
        # if not discord.opus.is_loaded():
        #     raise RunTimeError('Opus failed to load')

        self.bot = discord.Client(loop=self.core.loop)

        self.bot.event(self.on_ready)
        self.bot.event(self.on_disconnect)
        self.bot.event(self.on_message)

        self.logger.info("Starting bot...")
        # self.bot.run(self.config.get("discord", "token"))
        self.discord_starting_task = self.core.loop.create_task(self.start_bot(self.config.get("discord", "token")))

    async def on_ready(self):
        self.logger.info(f'{self.bot.user} has connected to Discord!')

    async def on_disconnect(self):
        self.logger.error(f'{self.bot.user} has been disconnected from Discord!')

    async def on_message(self, message):
        self.logger.info(f'New message: "{message}"')

    # when someone is typing right now
    # todo: do i need this?
    async def on_typing(self, channel, user, when):
        pass

    # todo: use reactions for votes?
    #discord.on_reaction_add(reaction, user)
    #on_reaction_remove(reaction, user)¶
    #on_reaction_clear_emoji(
    #https://discordpy.readthedocs.io/en/latest/api.html?highlight=on_ready#discord.on_voice_state_update

    async def start_bot(self, token):
        while True:
            # noinspection PyBroadException
            try:
                await self.core.loop.create_task(self.bot.start(token))
            except CancelledError:
                self.logger.info("Starting task have been canceled")
                break
            except Exception as e:
                self.logger.error("Starting exception: %s", str(e))
                traceback.print_exc()

    def cleanup(self):
        self.logger.info("Destroying discord polling loop...")
        if self.discord_starting_task is not None:
            self.discord_starting_task.cancel()
        self.thread_pool.shutdown()
        self.logger.info("Polling have been stopped")

    # todo
    def notify_user(self, uid, message):
        self.logger.debug("Trying to notify user#%d" % uid)
        self.logger.debug("notify_user is not implemented" % uid)
        try:
            pass
            # user = User.get(User.core_id == uid)
        except peewee.DoesNotExist:
            self.logger.warning("Trying to notify nonexistent user#%d" % uid)
            return
        # self._send_text_message(user, message)

    #
    # async def message_handler(self, message):
    #     # noinspection PyBroadException
    #     try:
    #         if message.entities and any(e.type == "bot_command" for e in message.entities):
    #             await self.tg_handler(message, self.command)
    #         elif message.text:
    #             await self.tg_handler(message, self.download)
    #         elif message.audio:
    #             await self.tg_handler(message, self.add_audio_file)
    #         elif message.sticker:
    #             self.sticker_handler(message)
    #         else:
    #             self.file_handler(message)
    #     except Exception:
    #         traceback.print_exc()

    #
    # async def inline_query_handler(self, inline_query):
    #     # noinspection PyBroadException
    #     try:
    #         await self.tg_handler(inline_query, self.search)
    #     except Exception:
    #         traceback.print_exc()
    #
    # async def chosen_inline_result_handler(self, chosen_inline_result):
    #     # noinspection PyBroadException
    #     try:
    #         await self.tg_handler(chosen_inline_result, self.search_select)
    #     except Exception:
    #         traceback.print_exc()
    #
    # async def callback_query_handler(self, callback_query):
    #     # noinspection PyBroadException
    #     try:
    #         await self.tg_handler(callback_query, self.menu_handler)
    #     except Exception:
    #         traceback.print_exc()
    #
    # async def menu_handler(self, data, user):
    #     if data.data[0:2] == "//":
    #         return
    #
    #     path = data.data.split(":")
    #     if len(path) == 0:
    #         self.logger.error("Bad menu path: " + str(path))
    #         return
    #
    #     self.logger.debug("Menu path: " + str(path))
    #
    #     if path[0] == "-":
    #         path.pop(0)
    #         self._update_text_message(
    #             chat_id=data.message.chat.id,
    #             message_id=data.message.message_id,
    #             new_markup=telebot.types.InlineKeyboardMarkup()
    #         )
    #     else:
    #         user.menu_message_id = data.message.message_id
    #         user.menu_chat_id = data.message.chat.id
    #         user.save()
    #
    #     if path[0] == "main":
    #         self.send_menu_main(user)
    #
    #     elif path[0] == "queue":
    #         offset = int(path[1]) if len(path) >= 2 else 0
    #         self.send_menu_queue(user, offset)
    #
    #     elif path[0] == "lyrics":
    #         self.send_lyrics(user)
    #         self.send_menu_main(user)
    #
    #     elif path[0] == "my_tracks":
    #         self.send_menu_my_tracks(user)
    #
    #     elif path[0] == "song":
    #         song_id = int(path[1])
    #         self.send_menu_song(user, song_id)
    #
    #     elif path[0] == "vote":
    #         sign = path[1]
    #         song_id = int(path[2])
    #         self.core.vote_song(user.core_id, sign, song_id)
    #         self.send_menu_song(user, song_id)
    #
    #     elif path[0] == "raise_track":
    #         song_id = int(path[1])
    #         self.core.raise_track(user.core_id, song_id)
    #         self.send_menu_song(user, song_id)
    #
    #     elif path[0] == "skip_song":
    #         self.core.switch_track(user.core_id)
    #         self.send_menu_main(user)
    #
    #     elif path[0] == "admin" and path[1] == "stop_playing":
    #         self.core.stop_playback(user.core_id)
    #         self.send_menu_main(user)
    #
    #     elif path[0] == "admin" and path[1] == "delete":
    #         song_id = int(path[2])
    #         position = self.core.delete_track(user.core_id, song_id)
    #         offset = ((position - 1) // self.songs_per_page) * self.songs_per_page
    #         self.send_menu_queue(user, offset)
    #
    #     elif path[0] == "admin" and path[1] == "raise_user":
    #         handled_user_id = int(path[2])
    #         self.core.raise_user(user.core_id, handled_user_id)
    #         self.send_menu_admin_user(user, handled_user_id)
    #
    #     elif path[0] == "admin" and path[1] == "list_users":
    #         offset = int(path[2]) if len(path) >= 2 else 0
    #         self.send_menu_admin_list_users(user, offset)
    #
    #     elif path[0] == "admin" and path[1] == "user_info":
    #         handled_user_id = int(path[2])
    #         self.send_menu_admin_user(user, handled_user_id)
    #
    #     elif path[0] == "admin" and path[1] == "ban_user":
    #         handled_user_id = int(path[2])
    #         self.core.ban_user(user.core_id, handled_user_id)
    #         self.send_menu_admin_user(user, handled_user_id)
    #
    #     elif path[0] == "admin" and path[1] == "unban_user":
    #         handled_user_id = int(path[2])
    #         self.core.unban_user(user.core_id, handled_user_id)
    #         self.send_menu_admin_user(user, handled_user_id)
    #
    #     else:
    #         self.logger.error("Unknown menu: %s", str(path))
    #
    # async def tg_handler(self, data, method):
    #     user = self.init_user(data.from_user)
    #     try:
    #         await method(data, user)
    #     except UserBanned:
    #         self._show_blocked_msg(user)
    #     except PermissionDenied:
    #         self._show_access_denied(user)
    #
    # async def search(self, data, user):
    #     query = data.query.lstrip()
    #
    #     def message_callback(text):
    #         try:
    #             self._send_text_message(user, text)
    #         except telebot.apihelper.ApiException:
    #             pass
    #
    #     results = await self.core.search_action(user.id, query=query, message_callback=message_callback)
    #     if results is None:
    #         self.logger.warning("Search have returned None instead of results")
    #         return
    #
    #     self.logger.debug("Response from core: %d results" % len(results))
    #
    #     results_articles = []
    #     for song in results:
    #         results_articles.append(telebot.types.InlineQueryResultArticle(
    #             id=song['downloader'] + " " + song['id'],
    #             title=song['artist'],
    #             description=song['title'] + " {:d}:{:02d}".format(*list(divmod(song["duration"], 60))),
    #             input_message_content=telebot.types.InputTextMessageContent(
    #                 "// " + song['artist'] + " - " + song['title']
    #             ),
    #         ))
    #     self.bot.answer_inline_query(data.id, results_articles)
    #
    # async def search_select(self, data, user):
    #     downloader, result_id = data.result_id.split(" ")
    #     reply = self._send_text_message(user, "Запрос обрабатывается...")
    #
    #     def progress_callback(progress_msg):
    #         self._update_or_send_text_message(user, reply, progress_msg)
    #
    #     try:
    #         song, lp, gp = await self.core.download_action(
    #             user.id,
    #             result={"downloader": downloader, "id": result_id},
    #             progress_callback=progress_callback
    #         )
    #         self._send_song_added_message(user, reply, gp, song)
    #     except NotAccepted:
    #         self._send_error(user, "🚫 Внутренняя ошибка: ни один загрузчик не принял запрос")
    #     except DownloadFailed:
    #         self._send_error(user, "🚫 Не удалось загрузить песню")
    #     except UserRequestQuotaReached:
    #         self._show_quota_reached_msg(user)
    #
    # async def command(self, message, user):
    #
    #     handlers = {
    #         'start': self.start_handler,
    #         'broadcast': self.broadcast_to_all_users,
    #         'stop_playback': self.stop_playback,
    #         'stop_playing': self.stop_playback,
    #         'skip_song': self.skip_song,
    #         'skip': self.skip_song,
    #     }
    #
    #     for e in message.entities:
    #         if e.type != "bot_command":
    #             continue
    #
    #         command = message.text[e.offset + 1:e.offset + e.length]
    #
    #         if command not in handlers:
    #             self.logger.warning("Unknown command: %s" % command)
    #             return
    #
    #         handlers[command](message, user)
    #
    # async def download(self, message, user):
    #     self.logger.debug("Download: " + str(message.text))
    #     text = message.text
    #
    #     if text[0:2] == "//":
    #         return
    #
    #     reply = self._send_text_message(user, "Запрос обрабатывается...")
    #
    #     def progress_callback(progress_msg):
    #         self._update_or_send_text_message(user, reply, progress_msg)
    #
    #     try:
    #         song, lp, gp = await self.core.download_action(user.id, text=text, progress_callback=progress_callback)
    #         self._send_song_added_message(user, reply, gp, song)
    #     except NotAccepted:
    #         self._suggest_search(user, reply, text)
    #     except DownloadFailed:
    #         self._send_error(user, "🚫 Не удалось загрузить песню")
    #     except UserRequestQuotaReached:
    #         self._show_quota_reached_msg(user)
    #
    # async def add_audio_file(self, message, user):
    #     file_info = self.bot.get_file(message.audio.file_id)
    #
    #     reply = self._send_text_message(user, "Запрос обрабатывается...")
    #
    #     def progress_callback(progress_msg):
    #         self._update_or_send_text_message(user, reply, progress_msg)
    #
    #     file = {
    #         "id": message.audio.file_id,
    #         "duration": message.audio.duration,
    #         "size": message.audio.file_size,
    #         "info": file_info,
    #         "artist": message.audio.performer or "",
    #         "title": message.audio.title or "",
    #     }
    #
    #     try:
    #         song, lp, gp = await self.core.download_action(user.id, file=file, progress_callback=progress_callback)
    #         self._send_song_added_message(user, reply, gp, song)
    #     except NotAccepted:
    #         self._send_error(user, "🚫 Внутренняя ошибка: ни один загрузчик не принял запрос")
    #     except DownloadFailed:
    #         self._send_error(user, "🚫 Не удалось загрузить песню")
    #     except UserRequestQuotaReached:
    #         self._show_quota_reached_msg(user)
    #
    # # MENU RELATED #####
    #
    # def remove_old_menu(self, user):
    #
    #     # self.bot.edit_message_reply_markup(
    #     #     user.menu_chat_id, user.menu_message_id,
    #     #     reply_markup=telebot.types.InlineKeyboardMarkup()
    #     # )
    #
    #     if user.menu_message_id is not None and user.menu_chat_id is not None:
    #         try:
    #             self.bot.delete_message(user.menu_chat_id, user.menu_message_id)
    #         except Exception as e:
    #             self.logger.warning("Can't delete message: %s", str(e))
    #
    # @staticmethod
    # def build_markup(text):
    #     lines = text.splitlines(False)
    #     btn_re = re.compile(r"(?:^|\|\|)\s*(?P<text>(?:[^|\\]|\\\|)+)|"
    #                         r"(?P<attr>(?:[^|\\=]|\\.)+)\s*=\s*(?P<val>(?:[^|\\]|\\.)*)")
    #
    #     markup = telebot.types.InlineKeyboardMarkup()
    #
    #     for line in lines:
    #         line = line.strip()
    #         if line == "":
    #             continue
    #
    #         matches = btn_re.findall(line)
    #
    #         buttons = []
    #         btn = None
    #
    #         for match in matches:
    #             text = match[0].strip()
    #             if text != "":
    #                 btn = {"text": text}
    #                 buttons.append(btn)
    #             else:
    #                 btn[match[1].strip()] = match[2].strip()
    #
    #         m_row = []
    #         for b in buttons:
    #             if "callback_data" in b:
    #                 m_row.append(telebot.types.InlineKeyboardButton(
    #                     text=b["text"],
    #                     callback_data=b["callback_data"]
    #                 ))
    #             elif "switch_inline_query_current_chat" in b:
    #                 m_row.append(telebot.types.InlineKeyboardButton(
    #                     text=b["text"],
    #                     switch_inline_query_current_chat=b["switch_inline_query_current_chat"]
    #                 ))
    #
    #         markup.row(*m_row)
    #     return markup
    #
    # def send_menu_main(self, user):
    #     state = self.core.get_state(user.core_id)
    #
    #     message_text = env.get_template("main_menu_text.tmpl").render(**state)
    #     kb_text = env.get_template("main_menu_keyboard.tmpl").render(**state)
    #     kb = self.build_markup(kb_text)
    #
    #     self.remove_old_menu(user)
    #     self._send_text_message(user, message_text, reply_markup=kb)
    #
    # def send_menu_queue(self, user, offset):
    #     data = self.core.get_queue(user.core_id, offset, self.songs_per_page)
    #     data["offset"] = offset
    #     data["page"] = math.ceil(offset / self.songs_per_page) + 1
    #     data["next_offset"] = offset + self.songs_per_page
    #     data["prev_offset"] = max(offset - self.songs_per_page, 0)
    #     data["user"] = user
    #
    #     message_text = env.get_template("queue_text.tmpl").render(**data)
    #     kb_text = env.get_template("queue_keyboard.tmpl").render(**data)
    #     kb = self.build_markup(kb_text)
    #
    #     self.remove_old_menu(user)
    #     self._send_text_message(user, message_text, reply_markup=kb)
    #
    # def send_lyrics(self, user):
    #     state = self.core.get_state(user.core_id)
    #     message_text = env.get_template("track_lyrics_text.tmpl").render(**state)
    #     self._send_text_message(user, message_text)
    #
    # def send_menu_my_tracks(self, user):
    #     data = self.core.get_user_info_minimal(user.core_id)
    #
    #     message_text = env.get_template("my_tracks_text.tmpl").render(**data)
    #     kb_text = env.get_template("my_tracks_keyboard.tmpl").render(**data)
    #     kb = self.build_markup(kb_text)
    #
    #     self.remove_old_menu(user)
    #     self._send_text_message(user, message_text, reply_markup=kb)
    #
    # def send_menu_song(self, user, song_id):
    #     data = self.core.get_song_info(user.core_id, song_id)
    #     data["user"] = user
    #     if data["song"] is not None:
    #         data["author"] = self.core.get_user_info_minimal(data["song"].user_id)["info"]
    #         data["list_offset"] = ((data["global_position"] - 1) // self.songs_per_page) * self.songs_per_page
    #     else:
    #         data["list_offset"] = 0
    #
    #     message_text = env.get_template("song_info_text.tmpl").render(**data)
    #     kb_text = env.get_template("song_info_keyboard.tmpl").render(**data)
    #     kb = self.build_markup(kb_text)
    #
    #     self.remove_old_menu(user)
    #     self._send_text_message(user, message_text, reply_markup=kb)
    #
    # def send_menu_admin_list_users(self, user, offset):
    #     data = self.core.get_users(user.core_id, offset, self.users_per_page)
    #     data["offset"] = offset
    #     data["page"] = math.ceil(offset / self.users_per_page) + 1
    #     data["next_offset"] = offset + self.users_per_page
    #     data["prev_offset"] = max(offset - self.users_per_page, 0)
    #
    #     users_cnt = data["cnt"]
    #
    #     message_text = "Нет ни одного пользователя" if users_cnt == 0 else "Количество пользователей: %d" % users_cnt
    #     kb_text = env.get_template("users_list_keyboard.tmpl").render(**data)
    #     kb = self.build_markup(kb_text)
    #
    #     self.remove_old_menu(user)
    #     self._send_text_message(user, message_text, reply_markup=kb)
    #
    # def send_menu_admin_user(self, user, handled_user_id):
    #     data = self.core.get_user_info(user.core_id, handled_user_id)
    #
    #     try:
    #         about_user_tg = User.get(User.core_id == handled_user_id)
    #         if about_user_tg.login is None:
    #             login = self.bot.get_chat(about_user_tg.tg_id).username
    #             about_user_tg.login = login
    #         data["about_user_tg"] = about_user_tg
    #     except KeyError:
    #         data["about_user_tg"] = None
    #
    #     message_text = env.get_template("user_info_text.tmpl").render(**data)
    #     kb_text = env.get_template("user_info_keyboard.tmpl").render(**data)
    #     kb = self.build_markup(kb_text)
    #
    #     self.remove_old_menu(user)
    #     self._send_text_message(user, message_text, reply_markup=kb)
    #
    # def notify_user(self, uid, message):
    #     self.logger.debug("Trying to notify user#%d" % uid)
    #     try:
    #         user = User.get(User.core_id == uid)
    #     except peewee.DoesNotExist:
    #         self.logger.warning("Trying to notify nonexistent user#%d" % uid)
    #         return
    #     self._send_text_message(user, message)
    #
    # def _send_text_message(self, user, message, reply_markup=None):
    #     try:
    #         return self.bot.send_message(user.tg_id, message, reply_markup=reply_markup)
    #     except telebot.apihelper.ApiException as e:
    #         self.logger.warning("Can't send message to user %d: %s", user.tg_id, str(e))
    #
    # def _update_text_message(self, chat_id, message_id, new_text=None, new_markup=None):
    #     try:
    #         reply = None
    #         if new_markup and not new_text:
    #             reply = self.bot.edit_message_reply_markup(
    #                 chat_id=chat_id, message_id=message_id, reply_markup=new_markup
    #             )
    #         elif new_text:
    #             reply = self.bot.edit_message_text(
    #                 new_text, chat_id=chat_id, message_id=message_id, reply_markup=new_markup
    #             )
    #         return reply
    #     except telebot.apihelper.ApiException as e:
    #         self.logger.warning("Can't edit message #%d in chat #%d: %s", message_id, chat_id, str(e))
    #
    # def _update_or_send_text_message(self, user, reply, new_text, new_markup=None):
    #     if reply is None:
    #         return self._send_text_message(user, new_text, new_markup)
    #     else:
    #         self._update_text_message(reply.chat.id, reply.message_id, new_text, new_markup)
    #         return reply
    #
    # def _send_greeting_message(self, user):
    #     try:
    #         self.bot.send_message(user.tg_id, help_message, disable_web_page_preview=True)
    #     except telebot.apihelper.ApiException as e:
    #         self.logger.warning("Can't send message to user %d: %s", user.tg_id, str(e))
    #
    # def _send_song_added_message(self, user, reply, position, track):
    #     data = {
    #         "position": position,
    #         "track": track,
    #         "tracks_list": self.core.get_user_info_minimal(user.core_id)["songs_in_queue"],
    #     }
    #
    #     message_text = env.get_template("song_added_msg_text.tmpl").render(**data)
    #     self._update_or_send_text_message(user, reply, message_text)
    #
    # def _send_error(self, user, message):
    #     self._send_text_message(user, message)
    #
    # def _show_blocked_msg(self, user):
    #     try:
    #         self.bot.send_message(user.tg_id, "К вашему сожалению, вы были заблокированы :/")
    #
    #         if user.tg_id not in self.bamboozled_users:
    #             self.bamboozled_users.append(user.tg_id)
    #             self.bot.send_sticker(user.tg_id, data="CAADAgADiwgAArcKFwABQMmDfPtchVkC")
    #     except telebot.apihelper.ApiException as e:
    #         self.logger.warning("Can't send message to user %d: %s", user.tg_id, str(e))
    #
    # def _show_quota_reached_msg(self, user):
    #     self._send_error(user, "🛑 Превышена квота на количество запросов. Попробуйте позже")
    #
    # def _show_access_denied(self, user):
    #     self._send_error(user, "❌ Доступ запрещён")
    #
    # def _suggest_search(self, user, reply, text):
    #     kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    #     kb.row(telebot.types.InlineKeyboardButton(
    #         text="🔍 " + text,
    #         switch_inline_query_current_chat=text,
    #     ))
    #
    #     reply = self._update_or_send_text_message(
    #         user, reply, "Запрос не распознан. Нажмите на кнопку ниже, чтобы включить поиск"
    #     )
    #     if reply is not None:
    #         try:
    #             return self.bot.edit_message_reply_markup(reply.chat.id, reply.message_id, reply_markup=kb)
    #         except telebot.apihelper.ApiException as e:
    #             self.logger.warning(
    #                 "Can't edit message markup #%d in chat #%d: %s", reply.message_id, reply.chat.id, str(e)
    #             )
    #
    # # COMMANDS HANDLERS #####
    #
    # def broadcast_to_all_users(self, message, user):
    #     text = message.text.replace("/broadcast", "").strip()
    #     if len(text) == 0:
    #         self._send_text_message(user, "Сообщение не должно быть пустым")
    #     else:
    #         self.core.broadcast_message(user.core_id, text)
    #
    # def stop_playback(self, _message, user):
    #     self.core.stop_playback(user.core_id)
    #
    # def skip_song(self, _message, user):
    #     self.core.switch_track(user.core_id)
    #
    # def start_handler(self, _message, user):
    #     self._send_greeting_message(user)
    #     self.send_menu_main(user)
    #
    # # USER INITIALIZATION #####
    #
    # def init_user(self, user_info):
    #     try:
    #         user = User.get(User.tg_id == user_info.id)
    #         if user.first_name != user_info.first_name or user.last_name != user_info.last_name:
    #             user.first_name = user_info.first_name
    #             user.last_name = user_info.last_name
    #             user.save()
    #             self.core.set_user_name(user.core_id, user.full_name())
    #             self.logger.info("User name updated: " + user.full_name())
    #         return user
    #     except peewee.DoesNotExist:
    #         core_id = self.core.user_init_action()
    #         user = User.create(
    #             tg_id=user_info.id,
    #             core_id=core_id,
    #             login=user_info.username,
    #             first_name=user_info.first_name,
    #             last_name=user_info.last_name,
    #         )
    #         self.core.set_user_name(core_id, user.full_name())
    #         self._send_greeting_message(user)
    #         return user
    #
    # # USER MESSAGES HANDLERS #####
    #
    # def file_handler(self, message):
    #     try:
    #         self.bot.send_message(message.from_user.id, "К сожалению, ваш файл не определяется как музыкальный")
    #     except telebot.apihelper.ApiException as e:
    #         self.logger.warning("Can't send message to user %d: %s", message.from_user.id, str(e))
    #
    # def sticker_handler(self, message):
    #     try:
    #         self.bot.send_sticker(message.from_user.id, data="CAADAgADLwMAApAAAVAg-c0RjgqiVyMC")
    #     except telebot.apihelper.ApiException as e:
    #         self.logger.warning("Can't send message to user %d: %s", message.from_user.id, str(e))
