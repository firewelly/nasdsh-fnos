#!/bin/bash
# NasDSH 容器入口：准备数据目录 → 播种 dsh profile 模板 → 启动 sessiond（前台）
set -e

DATA="${NASDSH_DATA:-/data}"
mkdir -p "$DATA/home" "$DATA/dsh-home" "$DATA/logs"
export HOME="$DATA/home"
export DSH_HOME="$DATA/dsh-home"
export XDG_CACHE_HOME="$DATA/cache"
mkdir -p "$XDG_CACHE_HOME"

# dsh 的 Workspace 目录选择器从 HOME 打开。给 HOME/projects 建到各允许根的
# 符号链接，用户点 Workspaces → + → Home → projects → volume1 即可进入项目。
# 允许根优先取 NASDSH_ROOTS（非 UGOS 平台如 fnOS 的 /vol1），否则用 /volume*、/home。
if [ -n "${NASDSH_ROOTS:-}" ]; then
  ROOT_GLOB=""
  IFS=':' read -ra ROOT_LIST <<< "$NASDSH_ROOTS"
  for r in "${ROOT_LIST[@]}"; do
    [ -n "$r" ] && ROOT_GLOB="$ROOT_GLOB $r"
  done
else
  ROOT_GLOB="/volume* /home"
fi
mkdir -p "$HOME/projects"
for root in $ROOT_GLOB; do
  [ -d "$root" ] || continue
  name=$(basename "$root")
  if [ ! -e "$HOME/projects/$name" ] && [ ! -L "$HOME/projects/$name" ]; then
    ln -s "$root" "$HOME/projects/$name" 2>/dev/null || true
  fi
done

# ── /data 必须是持久卷 ──────────────────────────────────────────────
DATA_MNT=$(df -P "$DATA" 2>/dev/null | awk 'NR==2{print $6}')
ROOT_MNT=$(df -P / 2>/dev/null | awk 'NR==2{print $6}')
if [ "$DATA_MNT" = "$ROOT_MNT" ]; then
  echo "[nasdsh] ⚠️  /data 未挂载独立卷（与容器根同一文件系统）——"
  echo "[nasdsh] ⚠️  应用升级/重建时数据会丢失！请把 DATA_PATH 指到 NAS 数据卷"
fi

# ── 首次运行播种 profile；已有文件绝不覆盖（保留用户配置/凭据）──
seed() {
  src="$1"; dst="$2"
  if [ ! -e "$dst" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    echo "[nasdsh] seeded $(basename "$dst")"
  fi
}
seed /opt/dsh-home/cordis.patch.yml "$DSH_HOME/cordis.patch.yml"
seed /opt/dsh-home/profiles/web "$DSH_HOME/profiles/web"
seed /opt/dsh-home/profiles/headless "$DSH_HOME/profiles/headless"
seed /opt/dsh-home/profiles/dsh-tui "$DSH_HOME/profiles/dsh-tui"
chmod -R u+rwX "$DSH_HOME" 2>/dev/null || true

# 访问口令：安装参数经 compose 以 TERM_PIN 传入；落 0600 文件后清除环境变量。
# 变量存在但为空 = 用户在安装参数里清空了口令 → 删除旧文件（禁用鉴权）。
if [ "${TERM_PIN+x}" = "x" ]; then
  if [ -n "$TERM_PIN" ]; then
    printf '%s' "$TERM_PIN" > "$DATA/.term_pin"
    chmod 600 "$DATA/.term_pin"
    echo "[nasdsh] 访问口令已写入 $DATA/.term_pin（0600）"
  else
    rm -f "$DATA/.term_pin"
    echo "[nasdsh] 访问口令为空，已禁用（删除旧 .term_pin）"
  fi
  unset TERM_PIN
fi

# 可选出网代理 / npm 镜像
if [ -f "$DATA/proxy.env" ]; then
  set -a
  . "$DATA/proxy.env"
  set +a
  echo "[nasdsh] 已加载 proxy.env (HTTP_PROXY=${HTTP_PROXY:-无})"
fi
export NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"

# 空字符串的 Key 视为未设置，避免 provider 误判为“已配置”
for v in DEEPSEEK_API_KEY BIGMODEL_API_KEY BAILIAN_API_KEY TOKENPLAN_API_KEY \
         VOLCENGINE_API_KEY OPENCODE_GO_API_KEY; do
  eval "val=\${$v:-}"
  if [ -z "$val" ]; then
    unset "$v"
  fi
done

# 模型 Key 只在服务进程环境里；提示哪些已配置（不打印值）
for v in DEEPSEEK_API_KEY BIGMODEL_API_KEY BAILIAN_API_KEY TOKENPLAN_API_KEY \
         VOLCENGINE_API_KEY OPENCODE_GO_API_KEY; do
  eval "val=\${$v:-}"
  if [ -n "$val" ]; then
    echo "[nasdsh] 已注入 $v"
  fi
done

echo "[nasdsh] dsh $(dsh --version 2>/dev/null || echo 'n/a') · DSH_HOME=$DSH_HOME"

# 降权运行：Docker 自动创建的挂载目录可能属 root
if [ "$(id -u)" = "0" ]; then
  chown -R 1000:10 "$DATA" 2>/dev/null || true
  echo "[nasdsh] 已校正 $DATA 属主（1000:10），降权运行"
  exec setpriv --reuid=1000 --regid=10 --clear-groups python3 /srv/sessiond.py
fi
exec python3 /srv/sessiond.py
