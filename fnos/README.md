# fnOS 打包（.fpk，X86_64）

把 NasDSH 打成 fnOS 应用中心可安装的 `.fpk`：**负载内自带离线 Docker 镜像**
（`docker save|gzip`），安装/升级时 `docker load`，启停用 `docker run/rm` 管理
容器 `nasdsh`，不依赖 fnOS 应用框架的 Docker 编排。

## 打包（在 x86_64 + Docker 的机器上执行，如 fnOS 本机）

```bash
# 1) 构建镜像（或从离线包 docker load）
docker build -f core/Dockerfile -t nasdsh:0.1.0 core

# 2) 打 fpk（产物 fnos/dist/nasdsh-fnos-0.1.0.fpk，约 1GB）
python3 fnos/build_fpk.py
# 版本号读 fnos/fpk_root/manifest；--image 可指定本机其他 tag
```

## 安装（fnOS）

- 应用中心 → 手动安装 → 选择 `.fpk`；或 SSH：
  `sudo appcenter-cli install-fpk /path/to/nasdsh-fnos-0.1.0.fpk`
- 安装向导可填：项目根目录（逗号分隔多个）、数据目录（建议 SSD 数据卷）、
  允许根目录、访问口令 PIN。全部可留空用默认值。**安装器没有 API Key 字段**——
  装好后在工作台 Settings → Models 里配置，凭据存数据卷（0600），不进包/日志：
  - 项目根默认 `/vol1/1000/nasdsh-projects`（自动创建）
  - 数据默认 `<应用数据目录>/data`
  - 允许根默认 = 第一个项目根的顶层目录（如 `/vol1`）
- 桌面图标「NasDSH 工作台」→ 浏览器打开 `http://<NAS>:12704`。
- 应用启停 = 容器 `nasdsh` 启停；**卸载/停用保留数据**（var 目录与项目目录不动），
  Docker 镜像也保留（彻底清除：卸载后 `docker rmi nasdsh:<ver>` 并删 var 数据目录）。

## 结构

```
fnos/
├── build_fpk.py           # 打包脚本（tar.gz，无需 fnpack）
├── payload/ui/config      # 桌面图标/iframe 入口（port 12704）
└── fpk_root/
    ├── manifest           # appname=nasdsh, service_port=12704
    ├── cmd/               # main + service-setup（docker run 逻辑）+ 框架回调
    ├── config/            # privilege（run-as root）
    └── wizard/install     # 安装向导字段
```

## 隐私保证

- 安装包（fpk）只含：离线镜像（由 `core/` 构建，构建上下文不含任何凭据）、
  桌面入口与脚本；**不含模型 key / PIN / 凭据库**。
- 凭据只存在于运行时：安装向导写入 `<var>/*.conf`（0600）与容器 env，
  数据目录的 `.credentials.yaml`，均随数据目录走、不随包分发。
- `build_fpk.py` 打包完成后自动执行 `tools/verify_no_keys.py`，把产物逐层
  解包（fpk→app.tgz→docker 镜像）与运行时真实凭据值比对，**命中即构建失败
  并删除产物**；也可手动复核：
  `python3 tools/verify_no_keys.py fnos/dist/xxx.fpk`
- 安装向导只有路径与 PIN 字段，没有 API Key 字段——key 不经安装器、不落
  安装日志/向导变量文件。
- 启动日志对 `docker run` 参数做了脱敏（`-e` 值不落日志）。

## 升级

改 `fpk_root/manifest` 的 `version` → `docker build` 新镜像 → 重新 `build_fpk.py`
→ 应用中心升级。升级流程会 `docker load` 新镜像并在启动时重建容器；
数据目录与向导配置（var/*.conf）保留。

## 注意

- 端口固定 **12704**（manifest / payload/ui/config / cmd/service-setup 三处一致；
  改端口需要同步改这三处）。
- 镜像约 2.5GB，fpk 约 1GB——首次安装请确保系统分区余量充足，
  或把数据目录指到数据卷。
- 需要 fnOS 已启用 Docker 且版本 ≥ 20.10（fnOS 自带）。
