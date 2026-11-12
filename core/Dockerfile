# NasDSH —— 在 NAS 上运行 DeepSeek Harness（dsh web / dsh-TUI）
# 构建上下文 = core/（见 src/build.sh）
#   docker build -f core/Dockerfile -t nasdsh:<ver> core
ARG APT_MIRROR=mirrors.ustc.edu.cn
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG DSH_VERSION=0.2.1-rc.5
ARG DSH_TUI_VERSION=0.18.0

FROM node:24-bookworm-slim

ARG APT_MIRROR
ARG NPM_REGISTRY
ARG DSH_VERSION
ARG DSH_TUI_VERSION

# 终端/开发常用工具 + 中文 locale + dsh 插件安装所需的 node-gyp 工具链
RUN set -e; if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    else \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
        tmux python3 git curl ca-certificates procps less vim nano hostname \
        bash-completion lsof locales tzdata jq ripgrep unzip xz-utils sqlite3 \
        openssh-client build-essential \
    && sed -i 's/^# *\(zh_CN.UTF-8 UTF-8\)\s*$/\1/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

# dsh + dsh-TUI + pnpm（dsh plugin 依赖 pnpm 管理 profile 依赖）
RUN npm config set registry "$NPM_REGISTRY" \
    && npm install -g --no-audit --no-fund \
        pnpm@10.13.1 \
        "@deepseek-ai/dsh@${DSH_VERSION}" \
        "@deepseek-harness-tui/dsh-tui@${DSH_TUI_VERSION}" \
    && npm cache clean --force

# dsh profile 模板（首次启动时由 entrypoint 复制到 /data/dsh-home，不覆盖用户文件）
COPY dsh-home-template /opt/dsh-home

# 在镜像内预装 dsh-TUI profile，避免 NAS 首次启动时联网安装
ENV DSH_HOME=/opt/dsh-home
RUN dsh plugin --profile dsh-tui add "@deepseek-harness-tui/dsh-tui@${DSH_TUI_VERSION}" \
    && dsh --profile web --dump-config >/dev/null \
    && dsh --profile headless --dump-config >/dev/null \
    && rm -rf /opt/dsh-home/profiles/dsh-tui/.pnpm-store /root/.local/share/pnpm/store

# 运行用户（1000:10）需要能执行 nasdsh-update：让 npm 全局目录可写。
# 这是单用户容器，容器内的写权限边界由 Docker 提供；不授予宿主权限。
RUN chown -R 1000:10 /usr/local/lib/node_modules /usr/local/bin

# sessiond（tab UI + 会话 API + dsh web 前缀反代 + WS→tmux 桥）与前端
COPY sessiond.py /srv/sessiond.py
COPY www /srv/www
COPY tmux.conf /etc/tmux.conf
COPY profile.d/10-dsh-hint.sh /etc/profile.d/10-dsh-hint.sh
COPY bin/nasdsh-update bin/update /usr/local/bin/
COPY entrypoint.sh /entrypoint.sh
# Mac/OneDrive 上的源文件可能是 000/600，COPY 会原样保留 —— 必须显式放开读权限，
# 否则 uid 1000 运行时读不到 /srv/www 与 dsh profile 模板（eq14 实测踩坑）。
RUN chmod -R a+rX /srv /opt/dsh-home \
    && chmod 0755 /entrypoint.sh /usr/local/bin/nasdsh-update /usr/local/bin/update /etc/profile.d/10-dsh-hint.sh \
    && chmod 0644 /etc/tmux.conf /srv/sessiond.py \
    && mkdir -p /data

ENV LANG=zh_CN.UTF-8 \
    LC_CTYPE=zh_CN.UTF-8 \
    TERM=xterm-256color \
    NPM_CONFIG_REGISTRY=${NPM_REGISTRY}

EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
