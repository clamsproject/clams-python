ARG clams_version
FROM ghcr.io/clamsproject/clams-python-opencv4:$clams_version
LABEL description="clams-python-opencv4-tf2 image is shipped with clams-python, ffmpeg, opencv4 and tensorflow2 libraries"

RUN pip install tensorflow==2.*
