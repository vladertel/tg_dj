FROM python:3.8-buster

RUN apt-get update && \
    apt-get install -y vlc-bin vlc-plugin-base pulseaudio && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /usr/local/tg_dj /data
COPY web *.py /usr/local/tg_dj/

COPY core      /usr/local/tg_dj/core
COPY downloaders /usr/local/tg_dj/downloaders
COPY telegram   /usr/local/tg_dj/telegram
COPY discord_   /usr/local/tg_dj/discord_
COPY VLC   /usr/local/tg_dj/VLC
COPY web        /usr/local/tg_dj/web
COPY config-docker.ini /config.ini
COPY entrypoint.sh /entrypoint.sh

WORKDIR /data
EXPOSE 8910 1233 8080
STOPSIGNAL SIGINT

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
