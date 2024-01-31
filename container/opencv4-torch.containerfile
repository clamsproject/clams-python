ARG clams_version
FROM ghcr.io/clamsproject/clams-python-opencv4:$clams_version
LABEL org.opencontainers.image.description="clams-python-opencv4-torch image is shipped with clams-python, ffmpeg, opencv4, and PyTorch"

RUN pip install --no-cache-dir torch==1.*
