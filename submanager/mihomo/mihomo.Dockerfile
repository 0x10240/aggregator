FROM debian:12-slim

LABEL maintainer="0868398@gmail.com"

COPY mihomo-linux-amd64-compatible-go120 /usr/bin/mihomo

RUN mkdir -p /etc/mihomo/

CMD ["/usr/bin/mihomo", "-f", "/etc/mihomo/config.yaml"]
