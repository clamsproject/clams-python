ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-torch2 image is shipped with clams-python and PyTorch2"

RUN pip install --no-cache-dir torch==2.*

