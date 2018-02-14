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
                    self.user_info[int(user)] = userinfo

    def cleanup(self):
        cache_path = os.path.join(os.getcwd(), cacheDir)
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)
        for user in self.user_info:
            with open(os.path.join(cache_path, str(user)), 'w') as f:
                f.write(json.dumps(self.user_info[user], ensure_ascii=False))

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(commands=['stop_playing'])(self.stop_playing)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        self.bot.message_handler(content_types=['audio'])(self.audio_handler)
        # self.bot.message_handlers.append(self.bot._build_handler_dict)

    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            self.user_info[task["user"]]["state"] = 0
            if task["action"] == "ask_user":
                songs = task["songs"]
                self.user_info[task["user"]]["state"] = 1
                self.user_info[task["user"]]["array_of_songs"] = songs
                self.bot.send_message(task["user"], task["message"], reply_markup=generate_markup(songs))
            elif task["action"] == "user_message":
                self.bot.send_message(task["user"], task["message"])
            else:
                self.bot.send_message(task["user"], "DEBUG:\n" + str(task))

    def broadcast_to_all_users(self, message):
        for user in self.users_states:
            self.bot.send_message(user, message)

    def stop_playing(self, message):
        self.output_queue.put({
            "action": "stop_playing",
            "user": message.from_user.id
        })

    def vote_up(self):
        pass

    def vote_down(self):
        pass

    def start_handler(self, message):
        self.user_info[message.from_user.id] = {}
        self.user_info[message.from_user.id]["state"] = 0
        self.bot.send_message(message.from_user.id, "halo")

    def text_message_handler(self, message):
        user = message.from_user.id
        text = message.text
        if user not in self.user_info:
            self.user_info[user] = {}
            self.user_info[user]["state"] = 0

        if self.user_info[user]["state"] == 0:
            self.user_info[user]["state"] = 2
            request = {
                "user": user,
                "text": text,
                "action": "download"
            }
            self.output_queue.put(request)
            self.bot.send_message(user, "Your request is queued. Wait for response")
            return

        if self.user_info[user]["state"] == 1:
            if text == "No" or text == "None of these":
                self.bot.send_message(user, "Then ask me something else!")
                self.user_info[user]["array_of_songs"] = []
                self.user_info[user]["state"] = 0
                return
            try:
                songs = self.user_info[user]["array_of_songs"]
                self.user_info[user]["array_of_songs"] = []
            except KeyError:
                self.bot.send_message(user, "You did not ask me anything before")
                self.user_info[user]["state"] = 0
            else:
                m = compiled_regex.search(text)
                try:
                    number = int(m.group(0)) - 1
                except (ValueError, AttributeError):
                    self.bot.send_message(user, "Push any button below")
                    return
                print(number)
                if len(songs) <= number or number < 0:
                    self.bot.send_message(user, "Bad number")
                    return
                self.user_info[user]["state"] = 0
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
            self.bot.send_message(message.from_user.id, "Unsupported audio format... for now... maybe later")
