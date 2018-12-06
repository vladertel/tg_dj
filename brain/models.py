import peewee
import datetime
import os

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

        self.haters = []

    def __repr__(self):
        return "Song(title: %s, artist: %s, id: %d)".format(self.title, self.artist, self.id)

    def __str__(self):
        return "Song(title: %s, artist: %s, id: %d)".format(self.title, self.artist, self.id)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "user_id": self.user_id,
            "media": self.media,
            "haters": self.haters,
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