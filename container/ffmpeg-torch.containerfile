ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-torch image is shipped with clams-python, ffmpeg and PyTorch"

RUN pip install --no-cache-dir torch==1.*
