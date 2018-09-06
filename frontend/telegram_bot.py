import telebot
import threading
from queue import Queue
import re
import os
import json
from time import sleep

from .private_config import token
from .config import cacheDir, superusers

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


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".") and f != "bans"]


class TgFrontend():

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
        self.user_info = {}
        self.banned_users = []
        self.load_users()
        self.init_handlers()
        self.init_callbacks()

##### INITS #####
    def bot_init(self):
        while True:
            try:
                print("Loading bot")
                self.bot.polling(none_stop=True)
            except Exception as e:
                print("SEEMS LIKE INTERNET IS BROKEN")
                print(e)
                sleep(5)

    def load_users(self):
        files_dir = os.path.join(os.getcwd(), cacheDir)
        if not os.path.exists(files_dir):
            return
        files = get_files_in_dir(files_dir)
        for user in files:
            with open(os.path.join(os.getcwd(), cacheDir, user)) as f:
                try:
                    userinfo = json.load(f)
                except UnicodeDecodeError:
                    print("UnicodeDecodeError for user: " + str(user))  # or os.unlink?
                else:
                    if "history" not in userinfo:
                        userinfo["history"] = []
                    if "username" not in userinfo:
                        userinfo["username"] = None
                    if "last_ask" not in userinfo:
                        userinfo["last_ask"] = None
                    userinfo["state"] = 0
                    self.user_info[int(user)] = userinfo
        with open(os.path.join(cacheDir, "bans")) as f:
            self.banned_users = json.loads(f.read())

    def init_user(self, user, state=0, history=[], queue_entry="queue", qn=0, username=None, last_ask=None):
        self.user_info[user] = {}
        self.user_info[user]["state"] = state
        self.user_info[user]["username"] = username
        self.user_info[user]["history"] = history
        self.user_info[user]["queue_msg_id"] = None
        self.user_info[user]["queue_fsm"] = {
            "entry": queue_entry,
            "number": qn  # queue - page, song - sid
        }
        self.user_info[user]["last_ask"] = last_ask

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(commands=['broadcast'])(self.broadcast_to_all_users)
        self.bot.message_handler(commands=['get_info'])(self.get_user_info)
        self.bot.message_handler(commands=['admin'])(self.start_admin)
        self.bot.message_handler(commands=['ms'])(self.manual_start)
        self.bot.message_handler(commands=['stop_playing', 'stop'])(self.stop_playing)
        self.bot.message_handler(commands=['skip_song', 'skip'])(self.skip_song)
        self.bot.message_handler(commands=['/'])(lambda x: True)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        self.bot.message_handler(content_types=['audio'])(self.audio_handler)

    def init_callbacks(self):
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "vote")(self.vote_callback)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "main")(self.menu_main)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "song")(self.menu_song)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "list")(self.menu_list)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "dele")(self.menu_delete_song)
        self.bot.callback_query_handler(func=lambda x: x.data[0:5] == "admin")(self.admin_menus)
        self.bot.callback_query_handler(func=lambda x: True)(self.problem)

        self.bot.inline_handler(func=lambda x: True)(self.search)
        self.bot.chosen_inline_handler(func=lambda x: True)(self.search_select)

    def cleanup(self):
        cache_path = os.path.join(os.getcwd(), cacheDir)
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)
        for user in self.user_info:
            with open(os.path.join(cache_path, str(user)), 'w') as f:
                f.write(json.dumps(self.user_info[user], ensure_ascii=False))
        with open(os.path.join(cache_path, "bans"), 'w') as f:
            f.write(json.dumps(self.banned_users, ensure_ascii=False))
        print("TG - Users saved.")


#######################
# TG CALLBACK HANDLERS
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

    def admin_menus(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        submenu = data.data[6:]
        if submenu[:4] == "main":
            self.send_menu_admin(data.from_user.id)
        elif submenu[:4] == "lius":
            self.send_menu_admin_list_users(data.from_user.id, int(submenu[4:]))
        elif submenu[:4] == "user":
            self.send_menu_admin_user(data.from_user.id, int(submenu[4:]))
        elif submenu[:4] == "banu":
            self.send_menu_admin_ban_user(data.from_user.id, int(submenu[4:]))
        elif submenu[:4] == "uban":
            self.send_menu_admin_unban_user(data.from_user.id, int(submenu[4:]))
        elif submenu[:4] == "skip":
            self.send_menu_admin_skip_song(data.from_user.id)
        else:
            print("UNKNOWN ADMIN SUBMENU: " + submenu)

    def menu_song(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        self.output_queue.put({
            "action": "menu",
            "entry": "song",
            "user": data.from_user.id,
            "number": int(data.data[4:])
        })

    def menu_delete_song(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        self.output_queue.put({
            "action": "delete",
            "user": data.from_user.id,
            "number": int(data.data[4:])
        })

    def menu_list(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        self.output_queue.put({
            "action": "menu",
            "entry": "list",
            "user": data.from_user.id,
            "number": int(data.data[4:])
        })

    def queue_callback(self, data):
        pass

    def problem(self, data):
        print("UNHANDLED BUTTON CALLBACK MESSAGE")
        print(data)

    def vote_callback(self, data):
        if data.from_user.id in self.banned_users:
            return
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
        if data.from_user.id in self.banned_users:
            return

        self.output_queue.put({
            "action": "search",
            "qid": data.id,
            "query": data.query.lstrip(),
            "user": data.from_user.id
        })

    def search_select(self, data):
        if data.from_user.id in self.banned_users:
            return

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


##### MENU RELATED #####
    def listened_menu(self, task):
        menu = task["entry"]
        if menu == "main":
            self.send_menu_main(task["user"], task["qlen"], task["now_playing"])
        elif menu == "list":
            self.send_menu_list(task["user"], task["number"], task["lista"], task["lastpage"])
        elif menu == "song":
            self.send_menu_song(task["user"], task["number"], task["duration"], task["rating"],
                                task["position"], task["title"], task['superuser'])
        else:
            print("WRONG MENU entry: " + str(task["entry"]))

    def send_menu_admin(self, user):
        message_text = "Админка, меню для админов и вот это вот всё"
        kb = telebot.types.InlineKeyboardMarkup(row_width=1)
        kb.row(telebot.types.InlineKeyboardButton(text="Пропустить песню", callback_data="admin:skip"),
               telebot.types.InlineKeyboardButton(text="Пользователи", callback_data="admin:lius0"))
        kb.row(telebot.types.InlineKeyboardButton(text="🔄Обновить🔄", callback_data="admin:main"))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_admin_list_users(self, user, page):
        users = [[x, self.user_info[x]['username']] for x in self.user_info] # if x not in superusers
        start = page * 10
        if len(users) == 0:
            self.bot.send_message(user, "No users here :(")
            self.send_menu_admin(user)
            return
        if start > len(users):
            start = (len(users) // 10) * 10
        end = start + 10
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        users_to_send = users[start:end]
        for usera in users_to_send:
            button_text = str(usera[0])
            if usera[1] is not None:
                button_text += " (" + usera[1] + ")"
            kb.row(telebot.types.InlineKeyboardButton(text=button_text, callback_data="admin:user" + str(usera[0])))
        nav_buts = []
        if page > 0:
            nav_buts.append(telebot.types.InlineKeyboardButton(text="⬅️Туда", callback_data="admin:lius" + str(page - 1)))
        if end < len(users):
            nav_buts.append(telebot.types.InlineKeyboardButton(text="Сюда➡️", callback_data="admin:lius" + str(page + 1)))
        kb.row(*nav_buts)
        kb.row(telebot.types.InlineKeyboardButton(text="Назад", callback_data="admin:main"),
               telebot.types.InlineKeyboardButton(text="🔄Обновить🔄", callback_data="admin:lius" + str(page)))
        message_text = "Количество пользователей: {:d}\nСтраница:{:d}".format(len(users), page)
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_admin_unban_user(self, user, user_to_unban):
        try:
            self.banned_users.remove(user_to_unban)
        except ValueError:
            pass
        self.send_menu_admin_user(user, user_to_unban)

    def send_menu_admin_ban_user(self, user, user_to_ban):
        try:
            self.banned_users.remove(user_to_ban)
        except ValueError:
            pass
        self.banned_users.append(user_to_ban)
        self.send_menu_admin_user(user, user_to_ban)

    def send_menu_admin_skip_song(self, user):
        self.output_queue.put({
            "action": "skip_song",
            "user": user
        })
        self.send_menu_admin(user)

    def send_menu_admin_user(self, user, about_user):
        print(about_user)
        user_info = self.user_info[about_user]
        users = [x for x in self.user_info]
        try:
            ind = users.index(about_user)
            back_button_data = "admin:lius" + str(ind // 10)
        except ValueError:
            back_button_data = "admin:lius0"
        if user_info['username'] is None:
            un = self.bot.get_chat(about_user).username
            if un is not None:
                user_info['username'] = un
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        if about_user in self.banned_users:
            kb.row(telebot.types.InlineKeyboardButton(text="Разбанить нафиг", callback_data="admin:uban" + str(about_user)))
        else:
            kb.row(telebot.types.InlineKeyboardButton(text="Забанить нафиг", callback_data="admin:banu" + str(about_user)))
        kb.row(telebot.types.InlineKeyboardButton(text="Назад", callback_data=back_button_data),
               telebot.types.InlineKeyboardButton(text="🔄Обновить🔄", callback_data="admin:user" + str(about_user)))
        if user_info['username'] is not None:
            un = "Username: " + user_info['username'] + "\n"
        else:
            un = "\n"
        if len(user_info['history']) > 0:
            history = "\n".join(user_info['history'])
        else:
            history = "Ничего не заказывал"
        message_text = "Id: {:d}\n{:s}История заказов:\n{:s}".format(about_user, un, history)
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_main(self, user, qlen, now_playing):
        kb = telebot.types.InlineKeyboardMarkup(row_width=1)
        if now_playing is not None:
            message_text = "Сейчас играет: {:s}\nПесен в очереди: {:d}".format(now_playing, qlen)
            kb.row(telebot.types.InlineKeyboardButton(text="Очередь", callback_data="list0"))
        else:
            message_text = "Ничего не играет пока, будь первым!"
        kb.row(telebot.types.InlineKeyboardButton(text="🔍 Поиск музыки", switch_inline_query_current_chat=""))
        kb.row(telebot.types.InlineKeyboardButton(text="🔄Обновить🔄", callback_data="main"))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_list(self, user, page, lista, lastpage):
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        if lista == []:
            message_text = "Очередь пустая :("
        else:
            message_text = "Текущая очередь.\nВыбери песню, чтобы голосовать за или против нее\nСтраница: {:d}".format(page + 1)
        for song in lista:
            kb.row(telebot.types.InlineKeyboardButton(text=song.title, callback_data="song" + str(song.id)))
        direction_ = []
        if page > 0:
            direction_.append(telebot.types.InlineKeyboardButton(text="⬅️Туда", callback_data="list" + str(page - 1)))
        if not lastpage:
            direction_.append(telebot.types.InlineKeyboardButton(text="Сюда➡️", callback_data="list" + str(page + 1)))
        kb.row(*direction_)
        kb.row(telebot.types.InlineKeyboardButton(text="🔙Назад", callback_data="main"),
               telebot.types.InlineKeyboardButton(text="🔄Обновить🔄", callback_data="list" + str(page)))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_song(self, user, sid, duration, rating, position, title, superuser=False):
        strdur = "{:d}:{:02d}".format(*list(divmod(duration, 60)))
        base_str = "Песня: {}\nПродолжительность: {}\nРейтинг: {:d}\nМесто в очереди: {:d}"
        message_text = base_str.format(title, strdur, rating, position)
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(text="👍", callback_data="vote+" + str(sid)),
               telebot.types.InlineKeyboardButton(text="👎", callback_data="vote-" + str(sid)))
        if superuser:
            kb.row(telebot.types.InlineKeyboardButton(text="Удалить", callback_data="dele" + str(sid)))
        kb.row(telebot.types.InlineKeyboardButton(text="🔙Назад", callback_data="list" + str(position)),
               telebot.types.InlineKeyboardButton(text="🔄Обновить🔄", callback_data="song" + str(sid)))
        self.bot.send_message(user, message_text, reply_markup=kb)


# BRAIN LISTENER #####
    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            if task["user"] == "System":
                self.input_queue.task_done()
                continue
            action = task["action"]
            if task["user"] not in self.user_info:
                self.init_user(task["user"])
            self.user_info[task["user"]]["state"] = 0
            if action == "user_message":
                self.listened_user_message(task)
            if action == "edit_user_message":
                self.listened_edit_user_message(task)
            elif action == "confirmation_done":
                self.listened_confirmation_done(task)
            elif action == "menu":
                self.listened_menu(task)
            elif action == "search_results":
                self.listened_search_results(task)
            else:
                self.bot.send_message(193092055, "DEBUG:\n" + str(task),
                                      reply_markup=telebot.types.ReplyKeyboardRemove())
            self.input_queue.task_done()

# BRAIN LISTENERS  #####
    def listened_user_message(self, task):
        self.bot.send_message(task["user"], task["message"], reply_markup=telebot.types.ReplyKeyboardRemove())

    def listened_edit_user_message(self, task):
        self.bot.edit_message_text(task["new_text"], task["chat_id"], task["message_id"])

    def listened_confirmation_done(self, task):
        self.user_info[task["user"]]["state"] = 0

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


# UTILITY FUNCTIONS #####
    def broadcast_to_all_users(self, message):
        if message.from_user.id in superusers:
            text = message.text.lstrip("/broadcast ")
            if len(text) > 0:
                for user in self.user_info:
                    self.bot.send_message(user, text)
        else:
            self.bot.send_message(message.from_user.id, "You have no power here")

    def get_user_info(self, message):
        if message.from_user.id in superusers:
            try:
                num = int(message.text.lstrip("/get_info "))
            except ValueError:
                self.bot.send_message(message.from_user.id, "bad id")
            else:
                if num in self.user_info:
                    self.bot.send_message(message.from_user.id, str(self.bot.get_chat(num).__dict__))
                else:
                    self.bot.send_message(message.from_user.id, "no such user")
        else:
            self.bot.send_message(message.from_user.id, "You have no power here")

# COMMANDS #####
    def start_admin(self, message):
        if message.from_user.id in superusers:
            self.send_menu_admin(message.from_user.id)

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
        self.init_user(message.from_user.id, username=message.from_user.username)
        self.bot.send_message(message.from_user.id, help_message,
                              reply_markup=telebot.types.ReplyKeyboardRemove(),
                              disable_web_page_preview=True)
        self.output_queue.put({
            "action": "menu",
            "user": message.from_user.id,
            "entry": "main",
            "number": 0
        })

# USER MESSAGES HANDLERS #####
    def text_message_handler(self, message):
        user = message.from_user.id
        if user in self.banned_users:
            self.bot.send_message(user, "Похоже вас забанило :(",
                                  reply_markup=telebot.types.ReplyKeyboardRemove())
            return
        text = message.text
        if user not in self.user_info:
            self.init_user(user)
        self.user_info[user]["history"].append(text)

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
        user = message.from_user.id
        if user in self.banned_users:
            return
        if user not in self.user_info:
            self.init_user(user)
        self.user_info[user]["history"].append("sent audio with id:" + str(message.audio.file_id))
        # if message.audio.mime_type == "audio/mpeg3":
        file_info = self.bot.get_file(message.audio.file_id)

        reply = self.bot.send_message(user, "Запрос обрабатывается...")
        self.output_queue.put({
            "action": "download",
            "user": message.from_user.id,
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
