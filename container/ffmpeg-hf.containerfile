ARG clams_version
FROM ghcr.io/clamsproject/clams-python-ffmpeg-hf5:$clams_version
LABEL org.opencontainers.image.description="clams-python-ffmpeg-hf image is an alias for clams-python-ffmpeg-hf5 (latest HuggingFace/transformers)"
