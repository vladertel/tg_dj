FROM python:3

RUN apt-get update && \
    apt-get install -y vlc-nox && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /usr/local/tg_dj /data
COPY web *.py /usr/local/tg_dj/

COPY brain      /usr/local/tg_dj/brain
COPY downloader /usr/local/tg_dj/downloader
COPY frontend   /usr/local/tg_dj/frontend
COPY streamer   /usr/local/tg_dj/streamer
COPY web        /usr/local/tg_dj/web
COPY config-docker.ini /config.ini

WORKDIR /data
EXPOSE 8910 1233 8080

CMD mkdir -p db media media_fallback; \
    python /usr/local/tg_dj/create_db.py; \
    if [ -n "$DJ_telegram_api_url" ]; then sed -i 's|https://api.telegram.org/|'$DJ_telegram_api_url'|g' \
        $(python3 -c "import telebot.apihelper as t; print(t.__file__)"); fi; \
    python /usr/local/tg_dj/run.py -f /config.ini