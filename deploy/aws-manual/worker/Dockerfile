FROM python:3.12-slim

WORKDIR /app

# System deps for voice libs; keep minimal.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN python -m pip install --no-cache-dir --upgrade pip \
  && python -m pip install --no-cache-dir -e /app \
  && python -m pip install --no-cache-dir PyNaCl==1.5.0 discord-ext-voice-recv

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main"]
