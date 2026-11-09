# Full image already ships gcc/headers, so no apt-get is needed (bullseye apt mirrors are EOL).
FROM python:3.7-bullseye
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
COPY . /app
COPY docker/settings_local.py /app/gw2raidar/settings_local.py
RUN mkdir -p /app/log /data/uploads /data/static
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]
