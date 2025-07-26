ARG clams_version
FROM ghcr.io/clamsproject/clams-python-tf2:$clams_version
LABEL org.opencontainers.image.description="clams-python-tf2-hf image is shipped with clams-python, tensorflow2, and vairous huggingface libraries"

RUN pip install --no-cache-dir transformers[tf,tokenizers]==4.*
RUN pip install --no-cache-dir datasets

