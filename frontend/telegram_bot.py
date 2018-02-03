import telebot
import threading
from queue import Queue

from .config import token

def generate_markup():
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.row("Yes")
    markup.row("No")
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
        self.init_handlers()

    def init_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_handler)
        self.bot.message_handler(content_types=['text'])(self.text_message_handler)
        # self.bot.message_handlers.append(self.bot._build_handler_dict)

    def brain_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            if task["action"] == "ask_user" or task["action"] == "user_message":
                self.bot.send_message(task["user"], task["message"], reply_markup=generate_markup())
            else:
                self.bot.send_message(task["user"], "DEBUG:\n" + str(task))


    def start_handler(self, message):
        self.bot.send_message(message.from_user.id, "halo")

    def text_message_handler(self, message):
        user = message.from_user.id
        text = message.text
        if text == "Yes":
            request = {
                "user":user,
                "text":text,
                "action":"user_confirmed"
            }
        elif text == "No":
            self.bot.send_message(user,"Then ask me something else!")
        else:
            request = {
                "user":user,
                "text":text,
                "action":"download"
            }
        self.output_queue.put(request)