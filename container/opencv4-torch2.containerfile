ARG clams_version
FROM ghcr.io/clamsproject/clams-python-opencv4:$clams_version
LABEL org.opencontainers.image.description="clams-python-opencv4-torch2 image is shipped with clams-python, opencv4 (ffmpeg backend), and PyTorch2"

RUN pip install --no-cache-dir torch==2.*

