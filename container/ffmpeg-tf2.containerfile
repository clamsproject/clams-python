ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-tf2 image is shipped with clams-python, ffmpeg, and tensorflow2"

RUN apt-get install -y build-essential libhdf5-dev
RUN pip install "cython<3.0.0" pyyaml==5.4.1 --no-build-isolation
RUN pip install --no-cache-dir tensorflow==2.*
