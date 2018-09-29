#!/bin/sh
cd web
python3 server.py -a 0.0.0.0 -p 8080 dynamic/current_song_info.json
