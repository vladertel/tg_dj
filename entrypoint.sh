#!/usr/bin/env bash

mkdir -p db media media_fallback
python /usr/local/tg_dj/create_db.py
if [[ -n "$DJ_telegram_api_url" ]]
then
    sed -i 's|https://api.telegram.org/|'${DJ_telegram_api_url}'|g' \
        $(python3 -c "import telebot.apihelper as t; print(t.__file__)");
fi

exec python /usr/local/tg_dj/run.py -f /config.ini
