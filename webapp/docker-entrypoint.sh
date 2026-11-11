#!/bin/sh
# 容器启动：把镜像内置的上游产物铺到数据卷（数据卷为空时才有必要），然后启动应用。
set -eu

DATA_DIR="${WEBAPP_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/plugins/sonovel" "$DATA_DIR/plugins/tomato/bin" "$DATA_DIR/library" "$DATA_DIR/runtime"

if [ ! -f "$DATA_DIR/plugins/sonovel/app.jar" ] && [ -f /app/vendor/sonovel/app.jar ]; then
  echo "[entrypoint] 初始化 so-novel 发布包到 $DATA_DIR/plugins/sonovel"
  cp -a /app/vendor/sonovel/. "$DATA_DIR/plugins/sonovel/"
fi

if [ ! -x "$DATA_DIR/plugins/tomato/bin/Tomato-Novel-Downloader" ] \
   && [ -x /app/vendor/tomato/bin/Tomato-Novel-Downloader ]; then
  echo "[entrypoint] 初始化番茄下载器二进制到 $DATA_DIR/plugins/tomato/bin"
  cp -a /app/vendor/tomato/bin/Tomato-Novel-Downloader "$DATA_DIR/plugins/tomato/bin/"
  chmod +x "$DATA_DIR/plugins/tomato/bin/Tomato-Novel-Downloader"
fi

exec "$@"
