import peewee
import datetime
import os
import requests
import lxml.html

db = peewee.SqliteDatabase("db/dj_brain.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class User(BaseModel):
    id = peewee.PrimaryKeyField()
    name = peewee.TextField(null=True)
    banned = peewee.BooleanField(default=False)
    last_activity = peewee.DateTimeField(null=True)
    superuser = peewee.BooleanField(default=False)


class Request(BaseModel):
    user = peewee.ForeignKeyField(User)
    text = peewee.CharField()
    time = peewee.DateTimeField(default=datetime.datetime.now)


db.connect()


class Song:
    counter = 0

    def __init__(self, media_path, title, artist, duration, user_id, forced_id=None):
        if forced_id is None:
            self.__class__.counter += 1
            self.id = self.__class__.counter
        else:
            self.id = forced_id

        self.title = title
        self.artist = artist
        self.duration = duration
        self.user_id = user_id
        self.media = media_path

        self.lyrics = None

        self.haters = []

    def __repr__(self):
        return "Song(title: {}, artist: {}, id: {})".format(self.title, self.artist, self.id)

    def __str__(self):
        return "Song(title: {}, artist: {}, id: {})".format(self.title, self.artist, self.id)

    def to_dict(self=None):
        if self:
            return {
                "id": self.id,
                "title": self.title,
                "artist": self.artist,
                "duration": self.duration,
                "user_id": self.user_id,
                "media": self.media,
                "haters": self.haters,
            }
        else:
            return {
                "id": 0,
                "title": "",
                "artist": "",
                "duration": 1,
                "user_id": 0,
                "media": "",
                "haters": [],
            }

    def full_title(self):
        if self.artist is not None and len(self.artist) > 0 and self.title is not None and len(self.title) > 0:
            return self.artist + " — " + self.title
        elif self.artist is not None and len(self.artist) > 0:
            return self.artist
        elif self.title is not None and len(self.title) > 0:
            return self.title
        else:
            return os.path.splitext(os.path.basename(self.media))[0]

    def add_hater(self, user_id):
        if user_id not in self.haters:
            self.haters.append(user_id)

    def remove_hater(self, user_id):
        if user_id not in self.haters:
            self.haters.remove(user_id)

    @classmethod
    def from_dict(cls, song_dict):
        obj = cls(song_dict["media"], song_dict["title"], song_dict["artist"],
                  song_dict["duration"], song_dict["user_id"], forced_id=song_dict["id"])
        if "haters" in song_dict:
            obj.haters = song_dict["haters"]
        return obj

    def fetch_lyrics(self):
        print("Loading lyrics...")
        url = "http://lyrics.wikia.com/wiki/{0}:{1}".format(self.artist, self.title)
        lyrics_request = requests.get(url)
        if lyrics_request.status_code != 200:
            self.lyrics = ""
            return

        try:
            tree = lxml.html.fromstring(lyrics_request.text.replace("<br />", "\n"))
            lyrics = "\n".join(tree.xpath('//div[@class="lyricbox"]/text()'))
            self.lyrics = lyrics
        except Exception as e:
            self.lyrics = "[Ошибка разбора страницы: %s]" % e

    def has_lyrics(self):
        return self.lyrics is not None and self.lyrics != ""

    def get_lyrics(self):
        if self.lyrics is None:
            self.fetch_lyrics()
        return self.lyrics
