# syntax=docker/dockerfile:1

# ---- 阶段 1：只取官方 JRE 21，避免在最终镜像里装整套 JDK ----
FROM eclipse-temurin:21-jre AS jre

# ---- 阶段 2：运行本站 Web 应用 ----
FROM python:3.12-slim-bookworm

ARG SONOVEL_VERSION=1.12.0
ARG TOMATO_VERSION=2.4.16
ARG TARGETARCH=amd64

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBAPP_DATA_DIR=/data \
    WEBAPP_PORT=8080 \
    WEBAPP_HOST=0.0.0.0

COPY --from=jre /opt/java/openjdk /opt/jre
ENV JAVA_HOME=/opt/jre
ENV PATH=/opt/jre/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tar \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- 引用上游官方的发布产物（不编译、不改写它们的源码）----
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) SASSET="sonovel-linux_x64.tar.gz"; TASSET="TomatoNovelDownloader-Linux_amd64-v${TOMATO_VERSION}";; \
      arm64) SASSET="sonovel-linux_arm64.tar.gz"; TASSET="TomatoNovelDownloader-Linux_arm64-v${TOMATO_VERSION}";; \
      *) echo "不支持的架构: $TARGETARCH"; exit 1;; \
    esac; \
    mkdir -p /app/vendor/sonovel /app/vendor/tomato/bin /tmp/sonovel-x; \
    curl -fsSL -o /tmp/sonovel.tar.gz \
      "https://github.com/freeok/so-novel/releases/download/v${SONOVEL_VERSION}/${SASSET}"; \
    tar -xzf /tmp/sonovel.tar.gz -C /tmp/sonovel-x; \
    SROOT=""; \
    for d in /tmp/sonovel-x /tmp/sonovel-x/* /tmp/sonovel-x/*/*; do \
      if [ -f "$d/app.jar" ]; then SROOT="$d"; break; fi; \
    done; \
    if [ -z "$SROOT" ]; then echo "发布包里没有找到 app.jar"; exit 1; fi; \
    cp -a "$SROOT"/. /app/vendor/sonovel/; \
    curl -fsSL -o /app/vendor/tomato/bin/Tomato-Novel-Downloader \
      "https://github.com/zhongbai2333/Tomato-Novel-Downloader/releases/download/v${TOMATO_VERSION}/${TASSET}"; \
    chmod +x /app/vendor/tomato/bin/Tomato-Novel-Downloader; \
    rm -rf /tmp/sonovel.tar.gz /tmp/sonovel-x

COPY app ./app
COPY serve.py ./
COPY scripts ./scripts
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3).read()" || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "serve.py"]
