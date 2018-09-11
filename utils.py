import os
from mutagen.mp3 import MP3


def get_mp3_title_and_duration(path):
    audio = MP3(path)

    try:
        artist = str(audio.tags.getall("TPE1")[0][0])
    except IndexError:
        artist = None
    try:
        title = str(audio.tags.getall("TIT2")[0][0])
    except IndexError:
        title = None

    if artist is not None and title is not None:
        ret = artist + " — " + title
    elif artist is not None:
        ret = artist
    elif title is not None:
        ret = title
    else:
        ret = os.path.splitext(os.path.basename(path[:-4]))[0]

    return ret, audio.info.length


def make_caption(number, word_forms):
    if 10 < number % 100 < 20:
        return word_forms[0] + word_forms[5]
    for i in range(1, 5):
        if number % 10 == i:
            return word_forms[0] + word_forms[i]
    return word_forms[0] + word_forms[5]