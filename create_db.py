from core.models import User, Request, db as brain_db
from telegram.TelegramFrontend import TgUser, db as tg_bot_db
from discord_.DiscordComponent import DiscordUser, GuildChannel, db as discord_bot_db

# connect actually happens in core.DJ_Brain file, and connects when imported
brain_db.connect(reuse_if_open=True)
brain_db.create_tables([User, Request])

tg_bot_db.connect(reuse_if_open=True)
tg_bot_db.create_tables([TgUser])

discord_bot_db.connect(reuse_if_open=True)
discord_bot_db.create_tables([DiscordUser, GuildChannel])
