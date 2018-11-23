import os
from mutagen.mp3 import MP3
from unidecode import unidecode


def make_endless_unfailable(func):
    def wrapper(*args, **kwargs):
        while True:
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(e)
    return wrapper


def get_mp3_info(path):
    audio = MP3(path)

    if audio.tags is None:
        return os.path.splitext(os.path.basename(path))[0], int(audio.info.length)

    try:
        artist = str(audio.tags.getall("TPE1")[0][0])
    except IndexError:
        artist = None

    try:
        title = str(audio.tags.getall("TIT2")[0][0])
    except IndexError:
        title = None

    return title, artist, int(audio.info.length)


def make_caption(number, word_forms):
    if 10 < number % 100 < 20:
        return word_forms[0] + word_forms[5]
    for i in range(1, 5):
        if number % 10 == i:
            return word_forms[0] + word_forms[i]
    return word_forms[0] + word_forms[5]


def sanitize_file_name(file_name):
    valid_chars = '-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

    file_name = unidecode(file_name)
    return ''.join([c if c in valid_chars else "_" for c in file_name])
