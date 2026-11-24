FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_STATION_TTS_HOST=0.0.0.0
WORKDIR /srv/voice
RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 update \
    && apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY service.py .
USER 65532:65532
EXPOSE 8095
CMD ["python", "service.py"]
