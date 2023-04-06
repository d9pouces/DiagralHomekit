FROM python:3.11
LABEL Maintainer="github@19pouces.net"
ENV PYTHONUNBUFFERED 1
RUN mkdir /etc/diagralhomekit && pip3 install diagralhomekit
CMD ["python3", "-m", "diagralhomekit"]
