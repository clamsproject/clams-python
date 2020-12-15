ARG clams_version
FROM clamsproject/clams-python:$clams_version
LABEL description="clams-python image is a base image for CLAMS apps"

RUN apt-get update && apt-get install -y ffmpeg
RUN pip install ffmpeg-python==0.2.0
