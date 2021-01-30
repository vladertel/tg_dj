# bot.py
import asyncio

import concurrent.futures
from concurrent.futures import CancelledError
from typing import Optional

import discord
import logging
import traceback

import peewee

from .AbstractFrontend import AbstractFrontend, FrontendUserInfo
from .jinja_env import env

from brain.DJ_Brain import UserBanned, UserRequestQuotaReached, DownloadFailed, PermissionDenied, DjBrain
from downloader.exceptions import NotAccepted

db = peewee.SqliteDatabase("db/discord_bot.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class GuildChannel(BaseModel):
    guild_id = peewee.IntegerField(unique=True)
    channel_id = peewee.IntegerField(null=True)


class DiscordUser(BaseModel):
    discord_id = peewee.IntegerField(unique=True)
    username = peewee.CharField()
    core_id = peewee.IntegerField(unique=True)
    member_of = peewee.ForeignKeyField(GuildChannel)

    def mention(self):
        return f"<@{self.discord_id}>"


db.connect()

help_message = """Этот бот позволяет тебе управлять музыкой, которая играет на этом сервере: добавлять в плейлист любимые треки и голосовать против нелюбимых.

Есть несколько способов добавить свою музыку в очередь:
— Отправь '{0}search <твой запрос>' и выбери из списка
— Отправь ссылку на видео на ютубе (например '!link youtube.com/watch?v=dQw4w9WgXcQ')
— Отправь сам файл с музыкой или ссылку на него (!link <file>) 

Если встроенный поиск не находит то, что нужно, то, возможно, эти треки были удалены по требованию правообладателя. Попробуй поискать на YouTube.

Доступные комманды:
{1}
"""


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text  # or whatever


choice_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# noinspection PyMissingConstructor
class DiscordFrontend(AbstractFrontend):
    def __init__(self, config, discord_client: discord.Client):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config
        self.logger = logging.getLogger('discord.bot')
        self.logger.setLevel(getattr(logging, self.config.get("discord", "verbosity", fallback="warning").upper()))

        self.core: Optional[DjBrain] = None
        self.master = None
        self.bot: discord.Client = discord_client

        self.interval = 0.1

        self.songs_per_page = 7
        self.users_per_page = 7

        self.command_prefix = self.config.get("discord", "command_prefix", fallback="!")

        self.commands = {
            "help": self.help_command,
            "link": self.link_command,
            "skip": self.skip_command,
            "search": self.search_command,
            "set_text_channel": self.set_text_channel_command
        }

        self.thread_pool = concurrent.futures.ThreadPoolExecutor()
        self.discord_starting_task = None

        self.help_message = help_message.format(self.command_prefix, "\n".join([self.command_prefix + k for k in self.commands]))

        self.startup_notifications = {}

        # noinspection PyArgumentList
        # self.mon_tg_updates = Counter('dj_tg_updates', 'Telegram updates counter')

        # noinspection PyArgumentList
        # self.mon_tg_api_errors = Counter('dj_tg_api_errors', 'Telegram API errors')

    def bind_core(self, core: DjBrain):
        self.core = core
        self.bot_init()

    def bind_master(self, master):
        self.master = master

    def get_user_info(self, core_user_id: int) -> Optional[FrontendUserInfo]:
        try:
            ds_user: DiscordUser = DiscordUser.get(core_id=core_user_id)
        except peewee.DoesNotExist:
            return None
        # noinspection PyTypeChecker
        return FrontendUserInfo("Discord", ds_user.username, ds_user.discord_id)


    def bot_init(self):
        # discord.opus.load_opus()
        # if not discord.opus.is_loaded():
        #     raise RunTimeError('Opus failed to load')

        self.bot.event(self.on_ready)
        self.bot.event(self.on_disconnect)
        self.bot.event(self.on_message)

        self.logger.info("Starting bot...")
        self.discord_starting_task = self.core.loop.create_task(self.start_bot(self.config.get("discord", "token")))

    def get_user(self, user: DiscordUser):
        # noinspection PyTypeChecker
        return self.bot.get_user(user.discord_id)

    async def on_ready(self):
        self.logger.info(f'{self.bot.user} has connected to Discord!')
        # self.core.loop.create_task(self.greet_guilds())

    async def greet_guilds(self):
        for guild in self.bot.guilds:
            try:
                guild_channel = GuildChannel.get(guild_id=guild.id)
            except peewee.DoesNotExist:
                continue
            else:
                channel = self.bot.get_channel(guild_channel.channel_id)
                if channel is not None:
                    await channel.send("Я онлайн и готов прнимать заказы!")
        for user in self.startup_notifications:
            self._notify_user(user, self.startup_notifications[user])

        self.startup_notifications = {}

    async def on_disconnect(self):
        self.logger.error(f'{self.bot.user} has been disconnected from Discord!')

    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return
        if message.guild is None:
            # todo: think about it
            await message.channel.send(f'Я работаю только с серверами, прямые сообщения недоступны!')
            return
        try:
            guild_channel = GuildChannel.get(guild_id=message.guild.id)
        except peewee.DoesNotExist as e:
            guild_channel = None

        if guild_channel is None and not message.content.startswith(self.command_prefix + "set_text_channel"):
            await message.channel.send(
                f'Мой канал не выбран! Вызовите "{self.command_prefix}set_text_channel" в нужном канале')
            return

        user = self.init_user(message.author)

        if guild_channel is not None and message.channel.id != guild_channel.channel_id and guild_channel.channel_id is not None:
            return

        if message.content.startswith(self.command_prefix):
            command = message.content.split(" ")[0][1:]
            if command in self.commands:
                # noinspection PyArgumentList
                self.core.loop.create_task(self.handle_task(command, message, user))
            else:
                await message.channel.send(f'No such command! Do you need "{self.command_prefix}help"?')
            return

    async def handle_task(self, command: str, message: discord.Message, user: DiscordUser):
        handler = self.commands[command]
        try:
            # noinspection PyArgumentList
            await handler(message, user)
        except UserBanned:
            await message.channel.send(f"{user.mention()}, похоже вас заблокировало :(")
        except PermissionDenied:
            await message.channel.send(f"{user.mention()}, похоже у вас нет доступа :(")
        except NotAccepted:
            await message.channel.send("🚫 Внутренняя ошибка: ни один загрузчик не принял запрос")
        except DownloadFailed:
            await message.channel.send("🚫 Не удалось загрузить песню")
        except UserRequestQuotaReached:
            await message.channel.send("🚫 Твоя квота закончилась :(")

    async def help_command(self, message: discord.Message, user: DiscordUser):
        await message.channel.send(self.help_message)

    async def link_command(self, message: discord.Message, user: DiscordUser):
        text = remove_prefix(message.content.lstrip(), f"{self.command_prefix}link ")
        self.logger.debug("Download: " + message.content)

        progress_message = await message.channel.send("Запрос обрабатывается...")

        def progress_callback(new_progress_msg_text):
            asyncio.run_coroutine_threadsafe(progress_message.edit(content=new_progress_msg_text), self.core.loop)

        song, lp, global_position = await self.core.download_action(user.core_id, text=text, progress_callback=progress_callback)
        await self._send_song_added_message(message.channel, user, global_position)

    async def skip_command(self, message: discord.Message, user: DiscordUser):
        self.core.switch_track(user.core_id)

    async def search_command(self, message: discord.Message, user: DiscordUser):
        query = remove_prefix(message.content.lstrip(), f"{self.command_prefix}search ")

        def message_callback(text):
            asyncio.run_coroutine_threadsafe(message.channel.send(f'{message.author.mention}! {text}'), self.core.loop)

        results = await self.core.search_action(user.core_id, query=query, message_callback=message_callback, limit=10)
        if results is None:
            self.logger.warning("Search have returned None instead of results")
            return

        self.logger.debug("Response from core: %d results" % len(results))

        if len(results) == 0:
            await message.channel.send("Ничего не найдено :(")
            return

        elif len(results) > 1:
            for i in range(len(results)):
                results[i]['emoji'] = choice_emoji[i]

            rendered_template = env.get_template("search_msg.tmpl").render({"results": results})

            my_message = await message.channel.send(rendered_template)

            for i in range(len(results)):
                self.core.loop.create_task(my_message.add_reaction(results[i]['emoji']))

            self.core.loop.create_task(self.wait_for_search_reaction(my_message, results, user))

        else:
            self.core.loop.create_task(self._download_result(results[0], user, message.channel))

    async def wait_for_search_reaction(self, message_to_react: discord.Message, results, user_who_ordered: DiscordUser):
        def check(reaction: discord.Reaction, user: discord.User):
            if user_who_ordered.discord_id != user.id or message_to_react != reaction.message:
                return False
            for result in results:
                if (result['emoji']) == str(reaction.emoji):
                    return True
            return False

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=600.0, check=check)
            index = choice_emoji.index(str(reaction.emoji))
            desired_song = results[index]
            self.core.loop.create_task(
                self._download_result(desired_song, user_who_ordered, message_to_react.channel))
        except asyncio.TimeoutError:
            await message_to_react.channel.send('Опоздал, дальше я игнорю твой ответ.')
        except CancelledError:
            self.logger.info("Polling task have been canceled")

        except Exception as e:
            self.logger.error("Polling exception: %s", str(e))
            traceback.print_exc()

    async def _download_result(self, desired_song, discord_user: DiscordUser, channel: discord.TextChannel):
        progress_message = await channel.send("Запрос обрабатывается...")

        def progress_callback(new_progress_msg_text):
            asyncio.run_coroutine_threadsafe(progress_message.edit(content=new_progress_msg_text), self.core.loop)

        song, local_position, global_position = await self.core.download_action(
            discord_user.core_id,
            result=desired_song,
            progress_callback=progress_callback
        )
        await self._send_song_added_message(channel, discord_user, global_position)


    async def set_text_channel_command(self, message: discord.Message, user: DiscordUser):
        permission = message.channel.permissions_for(message.author)
        if permission.administrator:
            try:
                guild_channel = GuildChannel.get(guild_id=message.guild.id)
                if guild_channel.channel_id != message.channel.id:
                    guild_channel.channel_id = message.channel.id
                    guild_channel.save()
                    self.logger.info(f'guild {message.guild.name} updated text channel: {message.channel.name}')
            except peewee.DoesNotExist:
                guild_channel = GuildChannel.create(guild_id=message.guild.id, channel_id=message.channel.id)
                guild_channel.save()
                self.logger.info(f'guild {message.guild.name} updated text channel: {message.channel.name}')

            await message.channel.send(f'Теперь я работаю в этом канале. Ура')
            return guild_channel
        else:
            await message.channel.send(f'You have no power here! He-he')
            return None

    async def start_bot(self, token: str):
        while True:
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

    def accept_user(self, core_user_id: int) -> bool:
        try:
            user = DiscordUser.get(core_id=core_user_id)
            if user is not None:
                return True
        except peewee.DoesNotExist:
            return False
        return True

    def notify_user(self, core_user_id: int, message: str):
        if self.bot.is_ready():
            self._notify_user(core_user_id, message)
        else:
            self.startup_notifications[core_user_id] = message

    def _notify_user(self, core_user_id: int, message: str):
        self.logger.debug("Trying to notify user#%d" % core_user_id)
        try:
            user: DiscordUser = DiscordUser.get(core_id=core_user_id)
            guild: discord.Guild = self.bot.get_guild(user.member_of.guild_id)
            channel: discord.TextChannel = guild.get_channel(user.member_of.channel_id)
            asyncio.run_coroutine_threadsafe(channel.send(f'{user.mention()}, {message}'), self.core.loop)
        except peewee.DoesNotExist:
            self.logger.warning("Trying to notify nonexistent user#%d" % core_user_id)
            return

    def init_user(self, user_info: discord.Member) -> DiscordUser:
        try:
            user = DiscordUser.get(discord_id=user_info.id)
            if user.username != user_info.name:
                user.username = user_info.name
                user.save()
                self.core.set_user_name(user.core_id, user.username)
                self.logger.info("User name updated: " + user.username)
            return user
        except peewee.DoesNotExist:
            core_id = self.core.user_init_action()
            guild = GuildChannel.get_or_create(guild_id=user_info.guild.id)[0]
            user = DiscordUser.create(
                discord_id=user_info.id,
                core_id=core_id,
                username=user_info.name,
                member_of=guild
            )
            self.core.set_user_name(core_id, user.username)
            return user

    async def _send_song_added_message(self, channel: discord.TextChannel, discord_user: DiscordUser, global_position: int):
        await channel.send(f"{discord_user.mention()} Песня добавлена в очередь: {global_position}")