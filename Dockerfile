FROM python:3.7-buster

RUN apt-get update && \
    apt-get install -y vlc-bin vlc-plugin-base && \
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
COPY entrypoint.sh /entrypoint.sh

# Workaround for pytube issue 472
WORKDIR /usr/local/lib/python3.7/site-packages/pytube
COPY pytube.patch ./pytube.patch
RUN ls -lA && patch -p2 <pytube.patch && cat __main__.py

WORKDIR /data
EXPOSE 8910 1233 8080
STOPSIGNAL SIGINT

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
