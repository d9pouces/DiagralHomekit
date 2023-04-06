DiagralHomekit
==============

[![PyPI version](https://badge.fury.io/py/diagralhomekit.svg)](https://badge.fury.io/py/diagralhomekit)

Allow to control your Diagral alarm systems through Apple Homekit.


First, you need to create a configuration file `~/.diagralhomekit/config.ini` with connection details for all Diagral systems.

```ini
[diagral:Home]
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


**As many sensitive data must be stored in this configuration file, so you should create a dedicated email address and Diagral account.**


Plex sensor
-----------

A presence can be detected when a specified Plex player is playing something:
```ini
[plex:appletv_web]
server_token=[authentication token]
server_url=[url of your Plex server]
player_name=[Displayed name for the player]
player_device=None,
player_product=[Product name of the targeted player]
player_title=[Title of the targeted player]
player_address=[IP address of the targeted player]
```
Only one of the last four properties is required to match with the targeted player.
To get actual property values, you can use `curl`:

```bash
curl -H Accept:application/json -H X-Plex-Token:[authentication token] [url of your Plex server]/status/sessions
```

HTTP monitoring
---------------

You can monitor some websites, as air purifier sensors (no Homekit sensor is available for HTTP monitoring…):
```ini
[internet:website]
url=[url to check]
name=[Displayed name]
```

Weather monitoring
------------------

You can monitor weather, and emulate a presence when it will rain in the next 10 minutes:

```ini
[meteofrance:paris]
name=Paris
latitude=48.866667
longitude=2.333333
country=FR
region=Île-de-France
```

UPS monitoring
--------------

UPS can also be monitoring, as soon as NUT is locally installed (standard UPS monitoring server on Linux.
```
[ups:home]
name=eaton650
```
