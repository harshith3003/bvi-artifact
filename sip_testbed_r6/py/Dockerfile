FROM python:3.12-slim
# Debian's FFmpeg has no AMR-NB encoder, so use a static FFmpeg build that includes libopencore-amrnb.
# The build fails here (rather than later, silently) if the AMR encoder is missing.
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${ARCH}-static.tar.xz" -o /tmp/ff.tar.xz \
    && tar -xJf /tmp/ff.tar.xz -C /tmp && cp /tmp/ffmpeg-*-static/ffmpeg /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/ \
    && rm -rf /tmp/ff* \
    && ffmpeg -hide_banner -encoders | grep -E "libopencore_amrnb|libopus" \
    && ffmpeg -hide_banner -encoders | grep -q libopencore_amrnb
RUN pip install --no-cache-dir numpy cryptography
WORKDIR /app
COPY item1_fingerprint/fingerprint.py item1_fingerprint/digest_auth.py item1_fingerprint/digest_auth_v2.py item1_fingerprint/channel.py ./
COPY sip_testbed/py/sipmsg.py ./
COPY sip_testbed/bvi/thresholds.json ./thresholds.json
COPY sip_testbed_r6/py/*.py ./
ENV PYTHONUNBUFFERED=1 PYTHONWARNINGS=ignore::DeprecationWarning
