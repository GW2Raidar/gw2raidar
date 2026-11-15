# ---- .NET runtime, needed to run the Elite Insights CLI (the log parser); only its files are copied ----
FROM mcr.microsoft.com/dotnet/runtime:10.0 AS dotnet

# ---- build stage: full image has gcc/headers, so packages without wheels can compile ----
FROM python:3.7-bullseye AS builder
ENV PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

# Elite Insights CLI: official release from https://github.com/baaron4/GW2-Elite-Insights-Parser/releases
# The version is pinned because the site depends on the structure of EI's JSON output and on its
# encounter IDs. To upgrade, change both the version and the checksum of its GW2EICLI.zip.
ARG GW2EI_VERSION=v3.32.0.0
ARG GW2EI_SHA256=ffcd8578a333723f6ca23ba875bc8b1ac758bdb6888f473c4b5c0602d4d902dd
RUN curl -fsSL -o /tmp/GW2EICLI.zip \
        "https://github.com/baaron4/GW2-Elite-Insights-Parser/releases/download/${GW2EI_VERSION}/GW2EICLI.zip" \
    && echo "${GW2EI_SHA256}  /tmp/GW2EICLI.zip" | sha256sum -c - \
    && python -m zipfile -e /tmp/GW2EICLI.zip /opt/gw2ei \
    && rm /tmp/GW2EICLI.zip

# ---- runtime stage: slim image, only the virtualenv is carried over (no apt-get needed) ----
FROM python:3.7-slim-bullseye
# GW2EI_CLI is read by gw2raidar/settings.py; a .dll is run through `dotnet`.
# The image has no ICU libraries, so .NET runs in invariant-culture mode; EI asks for the "en-US"
# culture, which then needs predefined-only switched off.
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:/usr/share/dotnet:$PATH" \
    STATIC_ROOT=/app/staticfiles \
    DOTNET_ROOT=/usr/share/dotnet \
    GW2EI_CLI=/opt/gw2ei/GuildWars2EliteInsights-CLI.dll \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
    DOTNET_SYSTEM_GLOBALIZATION_PREDEFINED_CULTURES_ONLY=false
RUN useradd --system --uid 1000 --home-dir /app --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
COPY --from=builder /opt/gw2ei /opt/gw2ei
WORKDIR /app
COPY . /app
# Bake the static files into the image (served by WhiteNoise); no database needed for this step.
# /app/log and /data/uploads are the only places the app writes to.
RUN python manage.py collectstatic --noinput \
    && (python -m compileall -q raidar analyser eiparser gw2api gw2raidar || true) \
    && mkdir -p /app/log /data/uploads \
    && chown app:app /app/log /data/uploads
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000
# The entrypoint starts as root only to fix volume ownership, then drops to the "app" user.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]
