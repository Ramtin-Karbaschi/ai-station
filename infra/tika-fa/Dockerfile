FROM apache/tika@sha256:ecdd37e204308266b1f8e28569f8516ebd5b96d7a4518a71d3904710b20c03b3

USER root

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      tesseract-ocr-fas \
      tesseract-ocr-ara \
      tesseract-ocr-eng \
      tesseract-ocr-osd \
      fonts-noto-core \
      fonts-noto-extra \
      fonts-noto-ui-core \
      fonts-dejavu-core \
      fontconfig && \
    fc-cache -fv && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 9998
