import telebot
import threading
from queue import Queue
import re
import os
import json

from .private_config import token
from .config import cacheDir

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

# @bot.message_handler(commands=['start', 'help'])
# def command_help(message):
#     markup = types.InlineKeyboardMarkup()
#     itembtna = types.InlineKeyboardButton('a', switch_inline_query="")
#     itembtnv = types.InlineKeyboardButton('v', switch_inline_query="")
#     itembtnc = types.InlineKeyboardButton('c', switch_inline_query="")
#     markup.row(itembtna)
#     markup.row(itembtnv, itembtnc)
#     bot.send_message(message.chat.id, "Choose one letter:", reply_markup=markup)


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")]


class TgFrontend():

    def __init__(self):
        self.bot = telebot.TeleBot(token)
        self.botThread = threading.Thread(daemon=True, target=self.bot.polling, kwargs={"none_stop": True})
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

    def cleanup(self):
        cache_path = os.path.join(os.getcwd(), cacheDir)
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)
        for user in self.user_info:
            with open(os.path.join(cache_path, str(user)), 'w') as f:
                f.write(json.dumps(self.user_info[user], ensure_ascii=False))
        print("TG - Users saved.")

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(commands=['stop_playing', 'stop'])(self.stop_playing)
        self.bot.message_handler(commands=['skip_song', 'skip'])(self.skip_song)
        self.bot.message_handler(commands=['voteup', 'vote_up'])(self.vote_up)
        self.bot.message_handler(commands=['votedown', 'vote_down'])(self.vote_down)
        self.bot.message_handler(commands=['get_queue'])(self.get_queue)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        self.bot.message_handler(content_types=['audio'])(self.audio_handler)

    def print_true(self, arg):
        print(arg)
        return True

    def init_callbacks(self):
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "vote")(self.vote_callback)
        self.bot.callback_query_handler(func=lambda x: x.data[0:4] == "")(self.queue_callback)
        self.bot.callback_query_handler(func=lambda: True)(self.problem)

    def queue_callback(self, data):
        pass

    def problem(self, data):
        print("UNHANDLED CALLBACK MESSAGE")
        print(data)

    def vote_callback(self, data):
        if data.data[4] == "+":
            action = "vote_up"
        else:
            action = "vote_down"
        self.output_queue.put({
            "action": action,
            "sid": int(data.data[5:]),
            "user": data.from_user.id
        })

    def get_queue(self, message):
        self.output_queue.put({
            "action": "get_queue",
            "user": message.from_user.id,
            "page": 0
        })

#####  BRAIN LISTENERS  #####
    def listened_ask_user(self, task):
        songs = task["songs"]
        self.user_info[task["user"]]["state"] = 1
        self.bot.send_message(task["user"], task["message"], reply_markup=generate_markup(songs))

    def listened_user_message(self, task):
        self.bot.send_message(task["user"], task["message"], reply_markup=None)

    def listened_confirmation_done(self, task):
        self.user_info[task["user"]]["state"] = 0

    def listened_queue(self, task):
        if len(task['data']) <= 0:
            reply = self.bot.send_message(task["user"], "Queue is empty", reply_markup=None)
            self.input_queue.task_done()
            return
        data = "\n".join([str(x.id) + ". " + x.title +
                          " " + "{:d}:{:02d}".format(*list(divmod(x.duration, 60))) for x in task['data']])
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        for x in task['data']:
            kb.row(telebot.types.InlineKeyboardButton(text="👍 " + str(x.id), callback_data="vote+" + str(x.id)),
                    telebot.types.InlineKeyboardButton(text="👎 " + str(x.id), callback_data="vote-" + str(x.id)))
        if self.user_info[task["user"]]["queue_msg_id"] is not None:
            self.bot.delete_message(task["user"], self.user_info[task["user"]]["queue_msg_id"])
        reply = self.bot.send_message(task["user"], data, reply_markup=kb)
        # print(reply)
        self.user_info[task["user"]]["queue_msg_id"] = reply["message_id"]

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
            elif action == "queue" or action == "reload_rating":
                self.listened_queue(task)
            else:
                self.bot.send_message(task["user"], "DEBUG:\n" + str(task), reply_markup=None)
            self.input_queue.task_done()

    def broadcast_to_all_users(self, message):
        for user in self.users_states:
            self.bot.send_message(user, message)

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

    def vote_up(self, message):
        try:
            self.output_queue.put({
                "action": "vote_up",
                "user": message.from_user.id,
                "sid": int(message.text.split()[1])
            })
        except ValueError:
            self.bot.send_message(message.from_user.id, "No")

    def vote_down(self, message):
        try:
            self.output_queue.put({
                "action": "vote_up",
                "user": message.from_user.id,
                "sid": int(message.text.split()[1])
            })
        except ValueError:
            self.bot.send_message(message.from_user.id, "No")

    def start_handler(self, message):
        self.user_info[message.from_user.id] = {}
        self.user_info[message.from_user.id]["state"] = 0
        self.bot.send_message(message.from_user.id, "halo")

    def init_user(self, user, state=0, history=[], queue_entry="queue", qn=0):
        self.user_info[user] = {}
        self.user_info[user]["state"] = state
        self.user_info[user]["history"] = history
        self.user_info[user]["queue_msg_id"] = None
        self.user_info[user]["queue_fsm"] = {
            "entry": queue_entry,
            "number": qn  # queue - page, song - sid
        }
        # self.user_info[]

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
            self.bot.send_message(user, "Your request is queued. Wait for response", reply_markup=None)
            return

        if self.user_info[user]["state"] == 1:
            if text == "No" or text == "None of these":
                self.bot.send_message(user, "Then ask me something else!", reply_markup=None)
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
        if message.audio.mime_type == "audio/mpeg3":
            file_info = self.bot.get_file(message.audio.file_id)
            self.output_queue.put({
                "user": message.from_user.id,
                "file": message.audio.file_id,
                "duration": message.audio.duration,
                "action": "download",
                "file_size": message.audio.file_size,
                "file_info": file_info
            })
        else:
            self.bot.send_message(message.from_user.id, "Unsupported audio format... Now I accept only mp3 :(")
