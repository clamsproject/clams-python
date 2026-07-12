ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-torch2 image is shipped with clams-python, ffmpeg, and PyTorch2"

RUN pip install --no-cache-dir torch==2.*

# PyTorch ships Triton, which JIT-compiles a small host-side CUDA driver shim
# at runtime -- that needs a C compiler + libc headers. Keep it minimal
# (gcc + libc6-dev); build-essential is not required.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

