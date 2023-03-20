ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg:$clams_version
LABEL description="clams-python-ffmpeg-torch image is shipped with clams-python, ffmpeg and PyTorch"

RUN pip install torch==1.*
