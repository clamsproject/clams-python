ARG clams_version
FROM clamsproject/clams-python:$clams_version
LABEL description="clams-python-ffmpeg image is shipped with clams-python and PyTorch"

RUN pip install torch==1.8.1
