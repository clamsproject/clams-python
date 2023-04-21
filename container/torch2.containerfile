ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg image is shipped with clams-python and PyTorch2"

RUN pip install torch==2.*
