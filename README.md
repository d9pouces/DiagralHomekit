DiagralHomekit
==============

[![PyPI version](https://badge.fury.io/py/diagralhomekit.svg)](https://badge.fury.io/py/diagralhomekit)

Allow to control your Diagral alarm systems through Apple Homekit.


First, you need to create a configuration file `~/.diagralhomekit/config.ini` with connection details for all Diagral systems.

```ini
[system:Home]
name=[an explicit name for this system]
login=[email address of the Diagral account]
password=[password for the Diagral account]
imap_login=[IMAP login for the email address receiving alarm alerts]
imap_password=[IMAP password]
imap_hostname=[IMAP server]
imap_port=[IMAP port]
imap_use_tls=[true/1/on if you use SSL for the IMAP connection]
master_code=[a Diagral master code, able to arm or disarm the alarm]
system_id=[system id — see below]
transmitter_id=[transmitter id — see below]
central_id=[central id — see below]

```
`system_id`, `transmitter_id` and `central_id` can be retrieved with the following command, that prepares a configuration file:

```bash
python3 -m diagralhomekit --config-dir ~/.diagralhomekit --create-config 'diagral@account.com:password'
```

Then you can run the script:

```bash
python3 -m diagralhomekit --port 6666 --config-dir ~/.diagralhomekit -v 2
```
On the first launch, a QR code is displayed and can be scanned in Homekit, like any Homekit-compatible device.


You can send logs to [Loki](https://grafana.com/oss/loki/) with `--loki-url=https://username:password@my.loki.server/loki/api/v1/push`.
You can also send alerts to [Sentry](https://sentry.io/) with `--sentry-dsn=my_sentry_dsn`.

Everything can be configured by environment variables instead of arguments:

```bash
DIAGRAL_PORT=6666
DIAGRAL_CONFIG=/etc/diagralhomekit
DIAGRAL_SENTRY_DSN=https://sentry_dsn@sentry.io/42
DIAGRAL_LOKI_URL=https://username:password@my.loki.server/loki/api/v1/push
DIAGRAL_VERBOSITY=1
```

You can also run it with `docker-compose` with the following `compose.yaml` file:
```yaml
services:
  diagral_homekit:
    image: d9pouces/diagralhomekit:latest
    volumes:
    - ./config:/etc/diagralhomekit
    restart: always
    environment:
    - DIAGRAL_PORT=51826
    - DIAGRAL_CONFIG=/etc/diagralhomekit
    - DIAGRAL_SENTRY_DSN=
    - DIAGRAL_LOKI_URL=
    - DIAGRAL_VERBOSITY=1
    ports:
    - 51826:51826
```

**As many sensitive data must be stored in this configuration file, so you should create a dedicated email address and Diagral account.**
