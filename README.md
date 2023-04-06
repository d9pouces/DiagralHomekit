DiagralHomekit
==============

Allow to control your Diagral alarm systems through Homekit.

.. image:: https://pyup.io/repos/github/d9pouces/DiagralHomekit/shield.svg
     :target: https://pyup.io/repos/github/d9pouces/DiagralHomekit/
     :alt: Updates


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
python3 -m diagralhomekit -C ~/.diagralhomekit --create-config 'diagral@account.com:password'
```

Then you can run the daemon for the first time:

```python3 -m diagralhomekit -p 6666 -C ~/.diagralhomekit -v 2```

You can send logs to [Loki](https://grafana.com/oss/loki/) with `--loki-url=https://username:password@my.loki.server/loki/api/v1/push`.
You can also send alerts to [Sentry](https://sentry.io/) with `--sentry-dsn=my_sentry_dsn`.

**As many sensitive data must be stored in this configuration file, so you should create a dedicated email address and Diagral account.**
