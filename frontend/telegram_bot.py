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


def generate_markup(songs):
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True)
    i = 1
    for song in songs:
        dur = song["duration"]
        m = dur // 60
        s = dur - m * 60
        strdur = "{:d}:{:02d}".format(m, s)
        markup.row(str(i) + ". " + song["artist"] + " - " + song["title"] + " " + strdur)
        i += 1
    markup.row("None of these")
    return markup


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")]


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
                    pass  # or os.unlink?
                else:
                    if "history" not in userinfo:
                        userinfo["history"] = []
                    userinfo["state"] = 0
                    self.user_info[int(user)] = userinfo

    def init_user(self, user, state=0, history=[], queue_entry="queue", qn=0, username=None):
        self.user_info[user] = {}
        self.user_info[user]["state"] = state
        self.user_info[user]["username"] = username
        self.user_info[user]["history"] = history
        self.user_info[user]["queue_msg_id"] = None
        self.user_info[user]["queue_fsm"] = {
            "entry": queue_entry,
            "number": qn  # queue - page, song - sid
        }

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(commands=['broadcast'])(self.broadcast_to_all_users)
        self.bot.message_handler(commands=['get_info'])(self.get_user_info)
        self.bot.message_handler(commands=['stop_playing', 'stop'])(self.stop_playing)
        self.bot.message_handler(commands=['skip_song', 'skip'])(self.skip_song)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        self.bot.message_handler(content_types=['audio'])(self.audio_handler)

    def init_callbacks(self):
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "vote")(self.vote_callback)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "main")(self.menu_main)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "song")(self.menu_song)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "list")(self.menu_list)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "pick")(self.menu_pick)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "dele")(self.menu_delete_song)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "none")(self.menu_none_picked)
        self.bot.callback_query_handler(func=lambda x: True)(self.problem)

    def cleanup(self):
        cache_path = os.path.join(os.getcwd(), cacheDir)
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)
        for user in self.user_info:
            with open(os.path.join(cache_path, str(user)), 'w') as f:
                f.write(json.dumps(self.user_info[user], ensure_ascii=False))
        print("TG - Users saved.")


##### TG CALLBACK HANDLERS #####
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

    def menu_none_picked(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        self.bot.send_message(data.from_user.id, "Значит сформируй запрос по-другому")

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

    def menu_pick(self, data):
        try:
            self.bot.delete_message(data.from_user.id, data.message.message_id)
        except Exception as e:
            print("delete_message exception: " + str(e))
            return
        self.output_queue.put({
            "action": "user_confirmed",
            "user": data.from_user.id,
            "number": int(data.data[4:])
        })

    def queue_callback(self, data):
        pass

    def problem(self, data):
        print("UNHANDLED BUTTON CALLBACK MESSAGE")
        print(data)

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



    # def listened_queue(self, task):
    #     if len(task['data']) <= 0:
    #         reply = self.bot.send_message(task["user"], "Queue is empty", 
    #                                       reply_markup=telebot.types.ReplyKeyboardRemove())
    #         self.input_queue.task_done()
    #         return
    #     data = "\n".join([str(x.id) + ". " + x.title +
    #                       " " + "{:d}:{:02d}".format(*list(divmod(x.duration, 60))) for x in task['data']])
    #     kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    #     for x in task['data']:
    #         kb.row(telebot.types.InlineKeyboardButton(text="👍 " + str(x.id), callback_data="vote+" + str(x.id)),
    #                 telebot.types.InlineKeyboardButton(text="👎 " + str(x.id), callback_data="vote-" + str(x.id)))
    #     if self.user_info[task["user"]]["queue_msg_id"] is not None:
    #         self.bot.delete_message(task["user"], self.user_info[task["user"]]["queue_msg_id"])
    #     reply = self.bot.send_message(task["user"], data, reply_markup=kb)
    #     # print(reply)
    #     self.user_info[task["user"]]["queue_msg_id"] = reply.message_id

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
        elif menu == "ask":
            self.send_menu_ask(task["user"], task["message"], task["songs"])
        else:
            print("WRONG MENU entry: " + str(task["entry"]))

    def send_menu_main(self, user, qlen, now_playing):
        kb = telebot.types.InlineKeyboardMarkup(row_width=1)
        if now_playing is not None:
            message_text = "Now playing: {:s}\nSongs in queue: {:>3d}".format(now_playing, qlen)
            kb.row(telebot.types.InlineKeyboardButton(text="Queue", callback_data="list0"))
        else:
            message_text = "Nothing playing now, be the first!"
        kb.row(telebot.types.InlineKeyboardButton(text="Reload", callback_data="main"))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_list(self, user, page, lista, lastpage):
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        if lista == []:
            message_text = "Queue is empty :("
        else:
            message_text = "Page: {:d}".format(page + 1)
        for song in lista:
            kb.row(telebot.types.InlineKeyboardButton(text=song.title, callback_data="song" + str(song.id)))
        direction_ = []
        if page > 0:
            direction_.append(telebot.types.InlineKeyboardButton(text="Prev", callback_data="list" + str(page - 1)))
        if not lastpage:
            direction_.append(telebot.types.InlineKeyboardButton(text="Next", callback_data="list" + str(page + 1)))
        kb.row(*direction_)
        kb.row(telebot.types.InlineKeyboardButton(text="Back", callback_data="main"),
               telebot.types.InlineKeyboardButton(text="Reload", callback_data="list" + str(page)))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_ask(self, user, message, songs):
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        message_text = message
        i = 0
        for song in songs:
            kb.row(telebot.types.InlineKeyboardButton(
                text=song["artist"] + " - " + song["title"] +
                    " {:d}:{:02d}".format(*list(divmod(song["duration"], 60))),
                callback_data="pick" + str(i))
            )
            i += 1
        kb.row(telebot.types.InlineKeyboardButton(text="None of these",
                                                      callback_data="none"))
        self.bot.send_message(user, message_text, reply_markup=kb)

    def send_menu_song(self, user, sid, duration, rating, position, title, superuser=False):
        strdur = "{:d}:{:02d}".format(*list(divmod(duration, 60)))
        base_str = "Song: {}\nDuration: {}\nRating: {:d}\nPosition in queue: {:d}"
        message_text = base_str.format(title, strdur, rating, position)
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.row(telebot.types.InlineKeyboardButton(text="👍", callback_data="vote+" + str(sid)),
               telebot.types.InlineKeyboardButton(text="👎", callback_data="vote-" + str(sid)))
        if superuser:
            kb.row(telebot.types.InlineKeyboardButton(text="Remove", callback_data="dele" + str(sid)))
        kb.row(telebot.types.InlineKeyboardButton(text="Back", callback_data="list" + str(position)),
               telebot.types.InlineKeyboardButton(text="Reload", callback_data="song" + str(sid)))
        self.bot.send_message(user, message_text, reply_markup=kb)

##### BRAIN LISTENER #####
    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            action = task["action"]
            if task["user"] not in self.user_info:
                self.init_user(task["user"])
            self.user_info[task["user"]]["state"] = 0
            if action == "ask_user":
                self.listened_ask_user(task)
            elif action == "user_message":
                self.listened_user_message(task)
            elif action == "confirmation_done":
                self.listened_confirmation_done(task)
            elif action == "menu":
                self.listened_menu(task)
            else:
                self.bot.send_message(task["user"], "DEBUG:\n" + str(task),
                                      reply_markup=telebot.types.ReplyKeyboardRemove())
            self.input_queue.task_done()

#####  BRAIN LISTENERS  #####
    def listened_ask_user(self, task):
        songs = task["songs"]
        self.user_info[task["user"]]["state"] = 1
        self.bot.send_message(task["user"], task["message"], reply_markup=generate_markup(songs))

    def listened_user_message(self, task):
        self.bot.send_message(task["user"], task["message"], reply_markup=telebot.types.ReplyKeyboardRemove())

    def listened_confirmation_done(self, task):
        self.user_info[task["user"]]["state"] = 0

##### UTILITY FUNCTIONS #####
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
                if num is self.user_info:
                    self.bot.send_message(message.from_user.id, self.bot.get_chat(num).__dict__)
                else:
                    self.bot.send_message(message.from_user.id, "no such user")
        else:
            self.bot.send_message(message.from_user.id, "You have no power here")

##### COMMANDS #####
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
        self.bot.send_message(message.from_user.id, "help will be here",
                              reply_markup=telebot.types.ReplyKeyboardRemove())
        self.output_queue.put({
            "action": "menu",
            "user": message.from_user.id,
            "entry": "main",
            "number": 0
        })

##### USER MESSAGES HANDLERS #####
    def text_message_handler(self, message):
        user = message.from_user.id
        text = message.text
        if user not in self.user_info:
            self.init_user(user)
        self.user_info[user]["history"].append(text)
        if self.user_info[user]["state"] == 0:
            if text == "None of these":
                return
            self.user_info[user]["state"] = 2
            request = {
                "user": user,
                "text": text,
                "action": "download"
            }
            self.output_queue.put(request)
            self.bot.send_message(user, "Your request is queued. Wait for response",
                                  reply_markup=telebot.types.ReplyKeyboardRemove())
            return

        if self.user_info[user]["state"] == 1:
            if text == "No" or text == "None of these":
                self.bot.send_message(user, "Then ask me something else!",
                                      reply_markup=telebot.types.ReplyKeyboardRemove())
                self.user_info[user]["state"] = 0
                return
            # try:
            #     songs = self.user_info[user]["array_of_songs"]
            # except KeyError:
            #     self.bot.send_message(user, "You did not ask me anything before")
            #     self.user_info[user]["state"] = 0
            # else:
            m = compiled_regex.search(text)
            try:
                number = int(m.group(0)) - 1
            except (ValueError, AttributeError):
                self.bot.send_message(user, "Push any button below")
                return
            if number < 0:
                self.bot.send_message(user, "Bad number")
                return
            self.output_queue.put({
                "user": user,
                "text": text,
                "action": "user_confirmed",
                "number": number
            })
            return

        if self.user_info[user]["state"] == 2:
            self.bot.send_message(user, "Stop it. Get some halp, your request will be processed soon")
            return

    def audio_handler(self, message):
        user = message.from_user.id
        if user not in self.user_info:
            self.init_user(user)
        self.user_info[user]["history"].append("sent audio with id:" + str(message.audio.file_id))
        # if message.audio.mime_type == "audio/mpeg3":
        file_info = self.bot.get_file(message.audio.file_id)
        self.output_queue.put({
            "user": message.from_user.id,
            "file": message.audio.file_id,
            "duration": message.audio.duration,
            "action": "download",
            "file_size": message.audio.file_size,
            "file_info": file_info
        })
        # else:
            # self.bot.send_message(message.from_user.id, "Unsupported audio format... For now I accept only mp3 :(")
