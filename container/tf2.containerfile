ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-tf2 image is shipped with clams-python and tensorflow2"

RUN apt-get install -y build-essential libhdf5-dev
RUN pip install --no-cache-dir tensorflow==2.*

