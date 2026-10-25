FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/citrackastra
# NVIDIA wheels include their userspace CUDA runtime. The host supplies the driver.
RUN pip install --no-cache-dir torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu126
COPY pyproject.toml README.md LICENSE NOTICE.md ./
COPY third_party ./third_party
COPY citrackastra ./citrackastra
COPY wrapper.py bilayers_cli.py config.yaml ./
RUN pip install --no-cache-dir .
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 CITRACKASTRA_MODELS=/opt/models
ENTRYPOINT ["python", "/opt/citrackastra/wrapper.py"]
CMD ["--model-dir", "/opt/models", "--infolder", "/data/in", "--outfolder", "/data/out"]
