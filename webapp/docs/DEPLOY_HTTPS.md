# 用 Nginx + 域名 + HTTPS 部署

适用：Ubuntu/Debian，宿主机已有 Nginx 占用 80/443，应用容器只监听 `127.0.0.1:11252`。
本文所有路径以 `book.longyb.xyz` 为例，换成你的域名即可。

## 1. 容器只监听本机端口

`docker-compose.offline.yml` 里把端口改成只绑回环，公网流量一律走 Nginx：

```yaml
ports:
  - "127.0.0.1:11252:8080"
```

同时 `.env` 打开 Secure Cookie（**必须**配合 HTTPS，否则浏览器不带 Cookie、登录会失败）：

```bash
WEBAPP_COOKIE_SECURE=1
```

```bash
docker compose -f docker-compose.offline.yml up -d --force-recreate
```

## 2. Nginx 反代站点

`/etc/nginx/sites-available/<域名>`：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name book.longyb.xyz;

    access_log /var/log/nginx/book.longyb.xyz.access.log;
    error_log  /var/log/nginx/book.longyb.xyz.error.log;

    client_max_body_size 4m;

    location / {
        proxy_pass http://127.0.0.1:11252;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 小说文件是流式下载：关掉缓冲、放宽超时
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_connect_timeout 30s;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/<域名> /etc/nginx/sites-enabled/<域名>
nginx -t && systemctl reload nginx
```

此时 `http://<域名>/healthz` 应该已经 200（先验证再签证书，排错更简单）。

## 3. 申请证书（certbot）

```bash
certbot --nginx -d <域名> --non-interactive --agree-tos --redirect --keep-until-expiring
```

> **国内服务器常见坑：IPv6 不可用导致 certbot 超时**
> 报错 `requests.exceptions.ReadTimeout: acme-v02.api.letsencrypt.org`，但 `curl` 明明是通的。
> 原因是 glibc/requests 优先解析到 IPv6，而机器没有 IPv6 出口。修复：
>
> ```bash
> echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf
> python3 -c "import socket;print(socket.getaddrinfo('acme-v02.api.letsencrypt.org',443,proto=socket.IPPROTO_TCP)[0])"
> # 期望首选是 IPv4
> ```

证书续期由 `certbot.timer` 自动完成，`systemctl list-timers | grep certbot` 可查。

## 4. 安全头（可选但推荐）

在 **443 的 server 块**里（不要放到 80 的跳转块）：

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

验证（注意 `/healthz` 只支持 GET，用 `curl -s -D -` 而不是 `-I`）：

```bash
curl -s -D - -o /dev/null https://<域名>/login | grep -iE 'strict-transport|x-frame'
```

## 5. 验收清单

```bash
curl -s -o /dev/null -w "https=%{http_code}\n" https://<域名>/healthz
curl -s -o /dev/null -w "http=%{http_code} -> %{redirect_url}\n" http://<域名>/healthz
curl -s -o /dev/null -w "public11252=%{http_code}\n" http://<服务器IP>:11252/healthz   # 期望 000
```

浏览器里再验证一次：登录 → 首页 → 后台，DevTools 里 `novel_session` 应为 `Secure` + `HttpOnly`。
