FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QT_QPA_PLATFORM=offscreen HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgl1 libglib2.0-0t64 libxkbcommon0 libdbus-1-3 libfontconfig1 libfreetype6 libxrender1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 openlips && useradd --uid 10001 --gid 10001 --no-create-home openlips \
    && mkdir /data && chown 10001:10001 /data
WORKDIR /app
COPY library_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY studio/ /app/studio/
COPY tools/ /app/tools/
COPY library_server/ /app/library_server/
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
USER 10001:10001
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["python", "-m", "library_server.health"]
CMD ["python", "-m", "library_server.app"]
