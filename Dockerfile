FROM pytorch/pytorch:2.11.0-cuda12.6-cudnn9-runtime@sha256:3bb77138e105723dd4ed760b82fb63d8310ae3a1afc58f76e0ecf0f776568d33 AS runtime
ARG DEBIAN_FRONTEND=noninteractive
# The official Ubuntu image uses system Python; changes stay inside this image.
ENV PIP_BREAK_SYSTEM_PACKAGES=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 xvfb xauth libgl1 libegl1 libopengl0 libgl1-mesa-dri libglib2.0-0 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 \
    libxcb-randr0 libxcb-xinput0 libx11-xcb1 libdbus-1-3 libfontconfig1 libfreetype6 libsm6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/citrackastra
# Reuse the official CUDA/PyTorch layers; the host supplies the NVIDIA driver.
# Keep dependencies independent of application and documentation changes.
COPY pyproject.toml ./
RUN pip install --no-cache-dir wheel setuptools \
    && SAM2_BUILD_CUDA=0 python -c "import subprocess,tomllib; p=tomllib.load(open('pyproject.toml','rb'))['project']; subprocess.check_call(['pip','install','--no-cache-dir','--no-build-isolation',*p['dependencies'],*p['optional-dependencies']['sam2'],*p['optional-dependencies']['movie']])"
COPY README.md LICENSE NOTICE.md ./
COPY third_party ./third_party
COPY citrackastra ./citrackastra
COPY wrapper.py bilayers_cli.py config.yaml ./
COPY plugin.json ./
COPY skills ./skills
COPY tools/movie_entrypoint.sh ./movie_entrypoint.sh
# SAM2's optional CUDA extension is unnecessary for image features. Build against
# the already installed CUDA PyTorch rather than downloading a second torch.
RUN pip install --no-cache-dir --no-deps --no-build-isolation . \
    && chmod +x /opt/citrackastra/movie_entrypoint.sh \
    && ln -s /models /opt/models
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 \
    CITRACKASTRA_MODELS=/opt/models QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 \
    MPLCONFIGDIR=/tmp/citrackastra-matplotlib XDG_CACHE_HOME=/tmp/citrackastra-cache
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="CITrackastra runtime with movie support" \
      org.opencontainers.image.source="https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.licenses="BSD-3-Clause"
ENTRYPOINT ["/opt/citrackastra/movie_entrypoint.sh"]
CMD ["--model-dir", "/opt/models", "--infolder", "/data/in", "--outfolder", "/data/out"]

FROM runtime AS tests
RUN pip install --no-cache-dir 'pytest>=8,<9'

FROM runtime AS production
