set("log.stdout",true)
set("log.file",false)
set("server.telnet",true)
set("server.timeout",-1.)

s = mksafe(request.queue())

# An output to the local soundcard
output.ao(s)

# An output to a local file, encoding
# in ogg/vorbis+ogg/theora
#output.file(%ogg(%theora,%vorbis),
#            fallible=true,
#            "z:\tmp\output.ogv",
#            s)

# An icecast output in AAC+ format
#output.icecast(%aacplus(bitrate=32),
#              fallible=true,
#              mount="test",
#              s)