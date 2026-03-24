FROM python:3.13-slim

# System dependencies: RTL-SDR, FFmpeg, PortAudio, audio libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    librtlsdr-dev \
    librtlsdr0 \
    rtl-sdr \
    ffmpeg \
    libportaudio2 \
    portaudio19-dev \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Blacklist kernel DVB driver so rtl-sdr can claim the USB device
RUN echo 'blacklist dvb_usb_rtl28xxu' > /etc/modprobe.d/blacklist-rtlsdr.conf

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project metadata first (cache-friendly layer)
COPY pyproject.toml ./
COPY src/ ./src/

# Install package with all optional dependency groups (transcribe + monitor)
RUN uv pip install --system \
    --group transcribe \
    --group monitor \
    -e .

# Audio WebSocket port
EXPOSE 9003

# Default: show help. Override CMD at runtime.
ENTRYPOINT ["vtms-sdr"]
CMD ["--help"]
