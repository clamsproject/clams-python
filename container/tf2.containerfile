ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-tf2 image is shipped with clams-python and tensorflow2"

RUN pip install tensorflow==2.*
