#!/bin/sh
python3 -i test_all.py | tee logfile$(date +'%Y_%m_%d_%H:%M').txt
