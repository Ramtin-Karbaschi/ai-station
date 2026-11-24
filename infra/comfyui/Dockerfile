FROM pytorch/pytorch:2.10.0-cuda13.0-cudnn9-runtime@sha256:1f57418aedd9a4d0d3a59646619e1d4f82cacc33817247cead4f749e1f452d4b

# ComfyUI v0.33.3 (commit 4da9e2dbead52fc1e68beae33fe3d7ad63b63241).
# Tarball checksum is pinned so a GitHub recompress fails closed.
ARG COMFYUI_REF=4da9e2dbead52fc1e68beae33fe3d7ad63b63241
ARG COMFYUI_TARBALL_SHA256=b8dd3d9a83d5cd583f61ec7c87a347298dc2182df0a1e4ef2c5db84d28cacd8c

USER root

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      ffmpeg \
      git \
      libgl1 \
      libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN curl -fsSL -o /tmp/comfyui.tar.gz \
      "https://github.com/Comfy-Org/ComfyUI/archive/${COMFYUI_REF}.tar.gz" && \
    echo "${COMFYUI_TARBALL_SHA256}  /tmp/comfyui.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/comfyui.tar.gz && \
    mv "ComfyUI-${COMFYUI_REF}" /opt/ComfyUI && \
    rm /tmp/comfyui.tar.gz

WORKDIR /opt/ComfyUI

RUN grep -viE '^(torch|torchvision|torchaudio)([=<>[:space:]]|$)' requirements.txt \
      > /tmp/comfyui-requirements.txt && \
    pip install --no-cache-dir -r /tmp/comfyui-requirements.txt && \
    rm /tmp/comfyui-requirements.txt

# ComfyUI-GGUF (ADR-018). Loads FLUX.2-dev Q4 GGUF on this 24 GiB GPU.
# Tarball checksum fails closed if GitHub recompresses the archive.
ARG COMFYUI_GGUF_REF=6ea2651e7df66d7585f6ffee804b20e92fb38b8a
ARG COMFYUI_GGUF_TARBALL_SHA256=688126d5c2b8c4ff061f56b23c3c6791ac01dc366e98d41ef1aaef374c36f283
RUN curl -fsSL -o /tmp/comfyui-gguf.tar.gz \
      "https://github.com/city96/ComfyUI-GGUF/archive/${COMFYUI_GGUF_REF}.tar.gz" && \
    echo "${COMFYUI_GGUF_TARBALL_SHA256}  /tmp/comfyui-gguf.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/comfyui-gguf.tar.gz && \
    mv "ComfyUI-GGUF-${COMFYUI_GGUF_REF}" /opt/ComfyUI/custom_nodes/ComfyUI-GGUF && \
    pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt && \
    rm /tmp/comfyui-gguf.tar.gz

COPY custom_nodes/ai_station_minimax /opt/ComfyUI/custom_nodes/ai_station_minimax

EXPOSE 8188

CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--disable-auto-launch"]
