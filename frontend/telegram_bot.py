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
        self.users_states = {}
        self.users_to_array_of_songs = {}
        self.init_handlers()

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        # self.bot.message_handlers.append(self.bot._build_handler_dict)

    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
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
            request = {
                "user": user,
                "text": text,
                "action": "download"
            }
            self.output_queue.put(request)
        elif self.users_states[user] == 1:
            if text == "No" or text == "None of these":
                self.bot.send_message(user, "Then ask me something else!")
                return
            try:
                songs = self.users_to_array_of_songs.pop(user)
            except:
                self.bot.send_message(user, "You did not ask me anything before")
            else:
                m = compiled_regex.search(text)
                try:
                    number = int(m.group(0)) - 1
                except ValueError:
                    self.bot.send_message(user, "Push any button below")
                    return
                self.users_states[user] = 0
                self.output_queue.put({
                        "user": user,
                        "text": text,
                        "action":"user_confirmed",
                        "number": number
                    })
