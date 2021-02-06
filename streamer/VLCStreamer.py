import time
import vlc
from prometheus_client import Gauge

from brain.models import Song
from streamer.AbstractStreamer import AbstractStreamer


# noinspection PyMissingConstructor
class VLCStreamer(AbstractStreamer):
    def __init__(self, config):
        self.config = config

        self.is_playing = False
        self.now_playing = None
        self.song_start_time = 0
        self.core = None

        # noinspection PyArgumentList
        self.mon_is_playing = Gauge('dj_is_playing', 'Is something paying now')
        self.mon_is_playing.set_function(lambda: 1 if self.is_playing else 0)

        self.vlc_instance = vlc.Instance()
        self.player = self.vlc_instance.media_player_new()
        self.init_handlers()

    def bind_core(self, core):
        self.core = core

    def init_handlers(self):
        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self.vlc_song_finished)

    def cleanup(self):
        self.player.stop()

    def vlc_song_finished(self, _event):
        self.is_playing = False
        self.now_playing = None
        self.core.loop.call_soon_threadsafe(self.core.track_end_event)

    def get_current_song(self):
        return self.now_playing

    def get_song_progress(self) -> int:
        return int(time.time() - self.song_start_time)

    def stop(self):
        self.player.stop()
        self.is_playing = False
        self.now_playing = None

    def switch_track(self, track: Song):
        uri = track.media
        vlc_options = self.config.get("streamer_vlc", "vlc_options")
        media = self.vlc_instance.media_new(uri, vlc_options, "sout-keep")
        self.player.set_media(media)
        self.player.play()
        self.is_playing = True
        self.now_playing = track
        self.song_start_time = time.time()


# found example
# import vlc
# finish = 0

# def SongFinished(event):
#     global finish
#     print "Event reports - finished"
#     finish = 1

# instance = vlc.Instance()
# player = instance.media_player_new()
# media = instance.media_new_path('vp1.mp3') #Your audio file here
# player.set_media(media)
# events = player.event_manager()
# events.event_attach(vlc.EventType.MediaPlayerEndReached, SongFinished)
# player.play()
# while finish == 0:
#         sec = player.get_time() / 1000
#         m, s = divmod(sec, 60)
#         print "%02d:%02d" % (m,s)

# class EventType(_Enum)
#  |  Event types.
#  |
#  |  Method resolution order:
#  |      EventType
#  |      _Enum
#  |      ctypes.c_uint
#  |      _ctypes._SimpleCData
#  |      _ctypes._CData
#  |      builtins.object
#  |
#  |  Data and other attributes defined here:
#  |
#  |  MediaDiscovererEnded = vlc.EventType.MediaDiscovererEnded
#  |
#  |  MediaDiscovererStarted = vlc.EventType.MediaDiscovererStarted
#  |
#  |  MediaDurationChanged = vlc.EventType.MediaDurationChanged
#  |
#  |  MediaFreed = vlc.EventType.MediaFreed
#  |
#  |  MediaListEndReached = vlc.EventType.MediaListEndReached
#  |
#  |  MediaListItemAdded = vlc.EventType.MediaListItemAdded
#  |
#  |  MediaListItemDeleted = vlc.EventType.MediaListItemDeleted
#  |
#  |  MediaListPlayerNextItemSet = vlc.EventType.MediaListPlayerNextItemSet
#  |
#  |  MediaListPlayerPlayed = vlc.EventType.MediaListPlayerPlayed
#  |
#  |  MediaListPlayerStopped = vlc.EventType.MediaListPlayerStopped
#  |
#  |  MediaListViewItemAdded = vlc.EventType.MediaListViewItemAdded
#  |
#  |  MediaListViewItemDeleted = vlc.EventType.MediaListViewItemDeleted
#  |
#  |  MediaListViewWillAddItem = vlc.EventType.MediaListViewWillAddItem
#  |
#  |  MediaListViewWillDeleteItem = vlc.EventType.MediaListViewWillDeleteIte...
#  |
#  |  MediaListWillAddItem = vlc.EventType.MediaListWillAddItem
#  |
#  |  MediaListWillDeleteItem = vlc.EventType.MediaListWillDeleteItem
#  |
#  |  MediaMetaChanged = vlc.EventType.MediaMetaChanged
#  |
#  |  MediaParsedChanged = vlc.EventType.MediaParsedChanged
#  |
#  |  MediaPlayerAudioDevice = vlc.EventType.MediaPlayerAudioDevice
#  |
#  |  MediaPlayerAudioVolume = vlc.EventType.MediaPlayerAudioVolume
#  |
#  |  MediaPlayerBackward = vlc.EventType.MediaPlayerBackward
#  |
#  |  MediaPlayerBuffering = vlc.EventType.MediaPlayerBuffering
#  |
#  |  MediaPlayerChapterChanged = vlc.EventType.MediaPlayerChapterChanged
#  |
#  |  MediaPlayerCorked = vlc.EventType.MediaPlayerCorked
#  |
#  |  MediaPlayerESAdded = vlc.EventType.MediaPlayerESAdded
#  |
#  |  MediaPlayerESDeleted = vlc.EventType.MediaPlayerESDeleted
#  |
#  |  MediaPlayerESSelected = vlc.EventType.MediaPlayerESSelected
#  |
#  |  MediaPlayerEncounteredError = vlc.EventType.MediaPlayerEncounteredErro...
#  |
#  |  MediaPlayerEndReached = vlc.EventType.MediaPlayerEndReached
#  |
#  |  MediaPlayerForward = vlc.EventType.MediaPlayerForward
#  |
#  |  MediaPlayerLengthChanged = vlc.EventType.MediaPlayerLengthChanged
#  |
#  |  MediaPlayerMediaChanged = vlc.EventType.MediaPlayerMediaChanged
#  |
#  |  MediaPlayerMuted = vlc.EventType.MediaPlayerMuted
#  |
#  |  MediaPlayerNothingSpecial = vlc.EventType.MediaPlayerNothingSpecial
#  |
#  |  MediaPlayerOpening = vlc.EventType.MediaPlayerOpening
#  |
#  |  MediaPlayerPausableChanged = vlc.EventType.MediaPlayerPausableChanged
#  |
#  |  MediaPlayerPaused = vlc.EventType.MediaPlayerPaused
#  |
#  |  MediaPlayerPlaying = vlc.EventType.MediaPlayerPlaying
#  |
#  |  MediaPlayerPositionChanged = vlc.EventType.MediaPlayerPositionChanged
#  |
#  |  MediaPlayerScrambledChanged = vlc.EventType.MediaPlayerScrambledChange...
#  |
#  |  MediaPlayerSeekableChanged = vlc.EventType.MediaPlayerSeekableChanged
#  |
#  |  MediaPlayerSnapshotTaken = vlc.EventType.MediaPlayerSnapshotTaken
#  |
#  |  MediaPlayerStopped = vlc.EventType.MediaPlayerStopped
#  |
#  |  MediaPlayerTimeChanged = vlc.EventType.MediaPlayerTimeChanged
#  |
#  |  MediaPlayerTitleChanged = vlc.EventType.MediaPlayerTitleChanged
#  |
#  |  MediaPlayerUncorked = vlc.EventType.MediaPlayerUncorked
#  |
#  |  MediaPlayerUnmuted = vlc.EventType.MediaPlayerUnmuted
#  |
#  |  MediaPlayerVout = vlc.EventType.MediaPlayerVout
#  |
#  |  MediaStateChanged = vlc.EventType.MediaStateChanged
#  |
#  |  MediaSubItemAdded = vlc.EventType.MediaSubItemAdded
#  |
#  |  MediaSubItemTreeAdded = vlc.EventType.MediaSubItemTreeAdded
#  |
#  |  RendererDiscovererItemAdded = vlc.EventType.RendererDiscovererItemAdde...
#  |
#  |  RendererDiscovererItemDeleted = vlc.EventType.RendererDiscovererItemDe...
#  |
#  |  VlmMediaAdded = vlc.EventType.VlmMediaAdded
#  |
#  |  VlmMediaChanged = vlc.EventType.VlmMediaChanged
#  |
#  |  VlmMediaInstanceStarted = vlc.EventType.VlmMediaInstanceStarted
#  |
#  |  VlmMediaInstanceStatusEnd = vlc.EventType.VlmMediaInstanceStatusEnd
#  |
#  |  VlmMediaInstanceStatusError = vlc.EventType.VlmMediaInstanceStatusErro...
#  |
#  |  VlmMediaInstanceStatusInit = vlc.EventType.VlmMediaInstanceStatusInit
#  |
#  |  VlmMediaInstanceStatusOpening = vlc.EventType.VlmMediaInstanceStatusOp...
#  |
#  |  VlmMediaInstanceStatusPause = vlc.EventType.VlmMediaInstanceStatusPaus...
#  |
#  |  VlmMediaInstanceStatusPlaying = vlc.EventType.VlmMediaInstanceStatusPl...
#  |
#  |  VlmMediaInstanceStopped = vlc.EventType.VlmMediaInstanceStopped
#  |
#  |  VlmMediaRemoved = vlc.EventType.VlmMediaRemoved
#  |
#  |  __ctype_be__ = <class 'vlc.EventType'>
#  |      Event types.
#  |
#  |  __ctype_le__ = <class 'vlc.EventType'>
#  |      Event types.
#  |
#  |  ----------------------------------------------------------------------
#  |  Methods inherited from _Enum:
#  |
#  |  __eq__(self, other)
#  |      Return self==value.
#  |
#  |  __hash__(self)
#  |      Return hash(self).
#  |
#  |  __ne__(self, other)
#  |      Return self!=value.
#  |
#  |  __repr__(self)
#  |      Return repr(self).
#  |
#  |  __str__(self)
#  |      Return str(self).
#  |
#  |  ----------------------------------------------------------------------
#  |  Data descriptors inherited from ctypes.c_uint:
#  |
#  |  __dict__
#  |      dictionary for instance variables (if defined)
#  |
#  |  __weakref__
#  |      list of weak references to the object (if defined)
#  |
#  |  ----------------------------------------------------------------------
#  |  Methods inherited from _ctypes._SimpleCData:
#  |
#  |  __bool__(self, /)
#  |      self != 0
#  |
#  |  __ctypes_from_outparam__(...)
#  |
#  |  __init__(self, /, *args, **kwargs)
#  |      Initialize self.  See help(type(self)) for accurate signature.
#  |
#  |  __new__(*args, **kwargs) from _ctypes.PyCSimpleType
#  |      Create and return a new object.  See help(type) for accurate signature.
#  |
#  |  ----------------------------------------------------------------------
#  |  Data descriptors inherited from _ctypes._SimpleCData:
#  |
#  |  value
#  |      current value
#  |
#  |  ----------------------------------------------------------------------
#  |  Methods inherited from _ctypes._CData:
#  |
#  |  __reduce__(...)
#  |      helper for pickle
#  |
#  |  __setstate__(...)
# (END)