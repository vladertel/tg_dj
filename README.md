# Telegram DJ

Бот для стриминга музыки с управлением через Телеграм.

## Конфигурация
Конфигурирование выполняется с помощью ini-файла, путь к 
которому передаётся в параметре `-f` (`--config-file`).
По-умолчанию читается файл `config.ini` в рабочей директории.

Кроме того, параметры можно задавать переменными окружения.
Переменные окружения имеют больший приоритет, нежели 
значения из конфигурационного файла.

Названия переменных окружения начинаются с префикса `DJ_`,
затем следует название секции (как в конфигурационном файле)
и ключ, разделённые символом подчёркивания. Например, 
порт, на котором будет доступен веб-интерфейс, можно задать
с помощью переменной окружения `DJ_web_server_listen_port`.

Для запуска бота требуется задать как минимум значение 
параметра `token` в секции `telegram`.

При запуске в докере рекомендуется использовать файл 
`docker-compose.override.yml`. Пример файла:
```yaml
version: '2'
services:
  tg_dj:
    environment:
      DJ_telegram_token: 123456789:abcdefghijklemopqrstuvwxyz123456789
  nginx:
    ports:
      - 8080:80
```

## Запуск
Для запуска требуется выполнить скрипт `run.py`. 
Перед первым запуском нужно создать базы данных, запустив
`create_db.py`

Для запуска в докере достаточно выполнить `docker-compose up`
 
