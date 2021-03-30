ARG clams_version
FROM clamsproject/clams-python-opencv4:$clams_version
LABEL description="clams-python-opencv4-torch image is shipped with clams-python, ffmpeg, opencv4, and PyTorch"

RUN pip install torch==1.8.1
