from brain.DJ_Brain import User, Request, db as brain_db
from frontend.telegram_bot import User as TgUser, db as tg_bot_db

brain_db.connect()
brain_db.create_tables([User, Request])

tg_bot_db.connect()
tg_bot_db.create_tables([TgUser])
