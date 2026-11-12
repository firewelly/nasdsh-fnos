# NasDSH 工作台 —— 飞牛 fnOS 版（.fpk 打包工程）

在飞牛 fnOS 上以应用中心 `.fpk` 形态运行 **NasDSH 工作台**（DeepSeek Harness on NAS）。
主项目（UGOS Pro 版、完整文档与隐私政策）见 **[firewelly/nasdsh](https://github.com/firewelly/nasdsh)**。

> 独立维护的 fnOS 适配，与其他同名/类似项目无分支关系。

## 仓库内容

| 目录 | 说明 |
|---|---|
| `core/` | 应用镜像构建源（Dockerfile + sessiond + Web UI + tmux 入口） |
| `fnos/` | .fpk 打包工程：`build_fpk.py`、manifest、安装向导、桌面入口 |
| `PRIVACY.md` | 隐私政策（与主仓库同源） |

安装包在 **Releases**：`nasdsh-fnos-<版本>.fpk`（负载内自带离线 Docker 镜像，约 1GB）。

## 快速开始

**打包**（x86_64 + Docker 机器，如 fnOS 本机）：

```bash
docker build -t nasdsh:0.1.0 core
python3 fnos/build_fpk.py          # 产物 fnos/dist/nasdsh-fnos-0.1.0.fpk
# 打包后自动执行凭据泄漏校验（tools/verify_no_keys.py 等价逻辑内建）
```

**安装**（fnOS 应用中心 → 手动安装，或 `sudo appcenter-cli install-fpk xxx.fpk`）：

- 安装向导可填：项目根目录（多个逗号分隔）、数据目录（建议 SSD 数据卷）、允许根目录、访问口令 PIN
- **安装器没有 API Key 字段**——装好后在工作台 Settings → Models 里配置，凭据存数据卷（0600），不进包/不落日志
- 桌面图标「NasDSH 工作台」→ `http://<NAS>:12704`；应用启停 = 容器 `nasdsh` 启停
- 卸载/停用保留数据与项目目录；彻底清除需手动 `docker rmi nasdsh:<ver>` 并删数据目录

## 规格与注意

- 端口固定 **12704**（manifest / payload/ui/config / cmd/service-setup 三处一致）
- 镜像约 2.5GB、fpk 约 1GB——首次安装确认系统分区余量，或数据目录指到数据卷
- 需 fnOS 已启用 Docker 且版本 ≥ 20.10

## 隐私保证

- fpk 只含离线镜像（构建上下文无凭据）、桌面入口与脚本；**不含模型 key / PIN / 凭据库**
- 打包完成后自动逐层解包产物与运行时真实凭据值比对，命中即构建失败并删除产物
- 明细见 [PRIVACY.md](PRIVACY.md) 与主仓库隐私政策

## 许可

MIT —— 见 [LICENSE](LICENSE)（Copyright (c) 2026 袁梦龙, GitHub: @firewelly）
