FROM pytorch/pytorch:2.9.1-cuda12.8-cudnn9-runtime@sha256:7b324d212a4450795b49edba9949b7cdc72429148a64e974334bfe5774d51385

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

COPY custom_nodes/ai_station_minimax /opt/ComfyUI/custom_nodes/ai_station_minimax

EXPOSE 8188

CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--disable-auto-launch"]
