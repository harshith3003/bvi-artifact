FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy cryptography
WORKDIR /app
COPY item1_fingerprint/fingerprint.py item1_fingerprint/digest_auth.py item1_fingerprint/channel.py ./
COPY sip_testbed/py/*.py ./
ENV PYTHONUNBUFFERED=1 PYTHONWARNINGS=ignore::DeprecationWarning
