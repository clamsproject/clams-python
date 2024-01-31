ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-tf2 image is shipped with clams-python, ffmpeg and tensorflow2 libraries"

RUN pip install --no-cache-dir tensorflow==2.*
