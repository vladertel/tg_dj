import telebot
import threading
from queue import Queue
import re

from .config import token

compiled_regex = re.compile(r"^\d+")

def generate_markup(songs):
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True)
    i = 1
    for song in songs:
        markup.row(str(i) + ". " + song["artist"] + " - " + song["title"])
        i += 1
    markup.row("None of these")
    return markup

class TgFrontend():

    def __init__(self):
        self.bot = telebot.TeleBot(token)
        self.botThread = threading.Thread(daemon=True, target=self.bot.polling, kwargs={"none_stop":True})
        self.botThread.start()
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.brainThread = threading.Thread(daemon=True, target=self.brain_listener)
        self.brainThread.start()
        # USER STATES:
        # 0 - basic
        # 1 - asked for confirmation
        # 2 - waiting for response
        self.users_states = {}
        self.users_to_array_of_songs = {}
        self.init_handlers()

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        self.bot.message_handler(content_types=['audio'])(self.audio_handler)
        # self.bot.message_handlers.append(self.bot._build_handler_dict)

    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            self.users_states[task["user"]] = 0
            if task["action"] == "ask_user":
                songs = task["songs"]
                self.users_states[task["user"]] = 1
                self.users_to_array_of_songs[task["user"]] = songs
                self.bot.send_message(task["user"], task["message"], reply_markup=generate_markup(songs))
            elif task["action"] == "user_message":
                self.bot.send_message(task["user"], task["message"])
            else:
                self.bot.send_message(task["user"], "DEBUG:\n" + str(task))

    def broadcast_to_all_users(self):
        pass

    def start_handler(self, message):
        self.users_states[message.from_user.id] = 0
        self.bot.send_message(message.from_user.id, "halo")

    def text_message_handler(self, message):
        user = message.from_user.id
        text = message.text
        if user not in self.users_states:
            self.users_states[user] = 0

        if self.users_states[user] == 0:
            self.users_states[user] = 2
            request = {
                "user": user,
                "text": text,
                "action": "download"
            }
            self.output_queue.put(request)
            return

        if self.users_states[user] == 1:
            if text == "No" or text == "None of these":
                self.bot.send_message(user, "Then ask me something else!")
                self.users_to_array_of_songs.pop(user, None)
                self.users_states[user] = 0
                return
            try:
                songs = self.users_to_array_of_songs.pop(user)
            except KeyError:
                self.bot.send_message(user, "You did not ask me anything before")
                self.users_states[user] = 0
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
                self.users_states[user] = 0
                self.output_queue.put({
                        "user": user,
                        "text": text,
                        "action":"user_confirmed",
                        "number": number
                    })
            return

        if self.users_states[user] == 2:
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

