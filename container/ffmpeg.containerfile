ARG clams_version
FROM ghcr.io/clamsproject/clams-python:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg image is shipped with clams-python and ffmpeg (+ python binding)"

RUN apt-get update && apt-get install -y ffmpeg
RUN pip install ffmpeg-python==0.2.*
