ARG clams_version
# llama.cpp's own CUDA server image (Ubuntu 24.04, CUDA 12.8 runtime,
# ffmpeg, llama-server and its backend libraries in /app), pinned by tag
# and digest. CLAMS builds no llama.cpp: to upgrade, bump both. Upstream
# compiles machine code for Ampere/Ada (8.6, 8.9) and Blackwell, and PTX
# for older GPUs (Maxwell to Turing, A100, Hopper), which the driver
# compiles at the first start; keep CUDA_CACHE_PATH (under /cache) on a
# volume so that happens once.
FROM ghcr.io/ggml-org/llama.cpp:server-cuda-b12169@sha256:5bb779a449a18d8f4333e9814e887746342fe555c528f5eabc92b2093e32673a
ARG clams_version
LABEL org.opencontainers.image.description="clams-python-llamaserver image is shipped with clams-python and llama.cpp's llama-server (experimental GGUF backend), on llama.cpp's CUDA image"

# Ubuntu blocks system-wide pip installs, so python packages live in a venv
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/clams
ENV PATH=/opt/clams/bin:$PATH

# upstream's binary finds its libraries in /app only when that is the
# working directory; apps also live in /app, but keep the path explicit
ENV LLAMA_SERVER=/app/llama-server
ENV LD_LIBRARY_PATH=/app

# same cache layout as the clams-python base image, plus the CUDA compile
# cache, so one volume at /cache keeps models and compiled kernels
ENV XDG_CACHE_HOME=/cache
ENV HF_HOME=/cache/huggingface
ENV TORCH_HOME=/cache/torch
ENV CUDA_CACHE_PATH=/cache/cuda-compute
ENV CUDA_CACHE_MAXSIZE=4294967296
RUN mkdir -p /cache && rm -rf /root/.cache && ln -s /cache /root/.cache

# fail the build if a library is missing (libcuda.so.1 comes from the host
# driver at run time)
RUN ! ldd /app/llama-server /app/*.so | grep 'not found' | grep -v 'libcuda.so.1'

RUN pip install --no-cache-dir "clams-python[llamaserver]==$clams_version"

# upstream starts llama-server; CLAMS apps set their own command
ENTRYPOINT []
