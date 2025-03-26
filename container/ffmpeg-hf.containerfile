ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg-torch2:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-hf image is shipped with clams-python, ffmpeg, and vairous huggingface libraries (PyTorch backend)"

RUN pip install --no-cache-dir transformers[torch,tokenizers]==4.*
RUN pip install --no-cache-dir datasets

