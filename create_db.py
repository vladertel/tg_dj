from brain.DJ_Brain import User, Request, db as brain_db
from frontend.telegram_bot import User as TgUser, db as tg_bot_db
import peewee

# connect actually happens in brain.DJ_Brain file, and connects when imported
try:
    brain_db.connect()
except peewee.OperationalError:
    pass
brain_db.create_tables([User, Request])

try:
    tg_bot_db.connect()
except peewee.OperationalError:
    pass
tg_bot_db.create_tables([TgUser])
