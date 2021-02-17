# DJ Bot

A bot for music streaming where users in charge of what is playing!

This bot can:
1) Take orders from: Telegram and/or Discord
2) Stream music to: http stream and/or Discord
3) Download tracks from: YouTube, direct links, search request
4) Fetch lyrics from: lyrics.wikia.com
5) Export some prometheus metrics
6) Moderate users with telegram admin

You can also access web page with music stream (look for `nginx.conf`)

## Configuration

Note: In order for Telegram bot to work you must enable inline mode and set inline feedback to 100

Configuration is done via .ini file and `--config-file` (`-f`) option. 
By default `config.ini` from working directory is taken .

Also every parameter can be set with env variable. 
Env variables have more priority over .ini file values

Env variables should be in this format in order to work:
`DJ_<config.ini_section>_<parameter_name>`
For example: `DJ_web_server_listen_port`

To launch this bot in a docker it's advised to use
`docker-compose.override.yml`. Exampl of file:
```yaml
version: '2'
services:
  app:
    environment:
      DJ_telegram_token: 123456789:abcdefghijklemopqrstuvwxyz123456789
  nginx:
    ports:
      - 8080:80
```

## Moderation

To make some user an admin you must:
1) Interact at least once with Telegram or Discord
2) Open the `dj_brain.db`
3) Edit the user.superuser field
Later on you have access to admin menus in telegram

## Launching

Before first launch you must create databases by running `create_db.py`.

To launch this bot simply run `run.py` with some standard configuration.

To launch in docker simply run `docker-compose up`

## Contributing

You are welcome!
