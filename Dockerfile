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
COPY enterypoint.sh /enterypoint.sh

WORKDIR /data
EXPOSE 8910 1233 8080
STOPSIGNAL SIGINT

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]