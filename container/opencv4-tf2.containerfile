ARG clams_version
FROM ghcr.io/clamsproject/clams-python-opencv4:$clams_version
LABEL org.opencontainers.image.description="clams-python-opencv4-tf2 image is shipped with clams-python, ffmpeg, opencv4 and tensorflow2 libraries"

RUN apt-get install -y build-essential libhdf5-dev
RUN pip install --no-cache-dir tensorflow==2.*
