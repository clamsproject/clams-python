ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg image is shipped with clams-python and PyTorch"

RUN pip install --no-cache-dir torch==1.*
