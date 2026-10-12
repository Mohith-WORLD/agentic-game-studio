# Multi-Agent Game Studio - Isolated Sandbox Runtime
# Purpose: Execute untrusted generated Pygame code under strict isolation.
# Security Constraints:
# - No network access (--network none)
# - Non-root execution (user 1000:1000)
# - Headless dummy SDL drivers (SDL_VIDEODRIVER=dummy, SDL_AUDIODRIVER=dummy)
# - Restricted resource limits (--memory 512m --cpus 1.0)
# - Read-only mounted source code

FROM python:3.11-slim

# Install minimal OS dependencies for headless Pygame/SDL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Pygame for the sandbox runner
RUN pip install --no-cache-dir pygame==2.6.1

# Create non-root unprivileged sandbox user
RUN useradd -u 1000 -m -s /bin/bash sandbox

# Configure headless execution environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SDL_VIDEODRIVER=dummy \
    SDL_AUDIODRIVER=dummy

USER sandbox
WORKDIR /workspace

CMD ["python", "--version"]
