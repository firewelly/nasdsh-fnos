# NasDSH 隐私政策 / NasDSH Privacy Policy

版本 v1.1 · 生效日期 2026-11-06 · 适用于 NasDSH 工作台 (`com.firewell.nasdsh`)

本政策同时提供中文与英文版本；如有歧义，以中文版本为准。
This policy is provided in Chinese and English. In case of discrepancy, the Chinese version prevails.

<!-- lang:zh:begin -->

## 一、运营者基本情况

- **应用名称**：NasDSH 工作台（内置 DeepSeek Harness）
- **应用标识**：`com.firewell.nasdsh`
- **运营者**：袁梦龙（个人开发者，无公司主体、无注册经营场所）
- **个人信息保护负责人**：袁梦龙
- **联系方式**：menglong_yuan@126.com ／ <https://github.com/firewelly/nasdsh/issues>
- **服务性质**：运行在用户自有 NAS 设备上的本地工具，免费、无内购、无广告

## 二、我们不收集什么

- 本应用**没有运营者侧服务器**，不上传、不收集、不分析您的项目文件、提示词、
  对话内容、代码、终端输出或任何个人信息。
- 本应用不含广告 SDK、用户画像、行为追踪或第三方统计 SDK。
- 本应用不设账号体系，不申请相机、通讯录、位置、麦克风、短信等任何设备权限。

## 三、按业务功能逐项披露

本应用只在您主动使用相应功能时处理下列信息，且**全部保存在您指定的 NAS
数据目录（安装参数 `DATA_PATH`）内**，不向运营者或任何第三方传输（第 4 项为
向您自行配置的服务商发起的请求，不属于向运营者传输）：

| # | 业务功能 | 涉及信息 | 目的 | 处理方式 | 存储位置 / 期限 |
|---|---|---|---|---|---|
| 1 | 访问口令（可选） | 您设置的访问口令（`TERMINAL_PIN`） | 校验访问者身份，防止局域网/远程他人打开工作台 | 口令由安装参数传入，启动时写入私有文件后立即从进程环境清除；登录采用挑战-应答：浏览器只提交 `sha256(nonce + sha256(口令))` 摘要，明文口令不出浏览器、不进 URL、不写日志；服务端仅保存摘要用于比对 | `DATA_PATH/.term_pin`（权限 0600）；不设置该参数即不收集；关闭口令或删除文件即删除 |
| 2 | AI 模型调用 | 您自行填写的模型 API Key | 让 dsh 调用您选择的模型服务商 | 由您在 dsh 界面或配置文件中填写；仅用于向该服务商发起请求 | `DATA_PATH`（dsh 凭据库，权限 0600）；可随时在 dsh 设置中删除 |
| 3 | 会话与工作区 | 会话记录、工作区路径、界面设置、运行日志 | 关窗保留、重开续用、故障排查 | 由 dsh / dsh-TUI 在本机读写 | `DATA_PATH/dsh-home`、`DATA_PATH/home`、`DATA_PATH/logs`；直到您删除 |
| 4 | 模型对话 | 提示词、上下文、工具调用结果 | 完成您发起的对话 | 直接由容器发往**您自行配置**的模型服务商端点；本应用不代理、不中转、不额外留存 | 请求内容不留存于本应用；服务商侧处理遵循其条款 |
| 5 | 出网代理（可选） | 代理地址、信任域名（`proxy.env`） | 让容器经您指定的代理出网、或允许额外访问域名 | 仅本机读取，写入容器进程环境 | `DATA_PATH/proxy.env`；删除文件即删除 |
| 6 | 插件 / MCP 连接器（可选） | 您安装的 dsh 插件与连接器配置 | 扩展 dsh 能力 | 由 dsh 在本机执行；是否联网取决于您装的插件 | `DATA_PATH/dsh-home/profiles`；卸载插件即删除 |

**安装包内不含任何预置凭据**：仓库与镜像不含 API Key、访问口令或任何账号信息，
打包流程会自动逐层扫描校验（`tools/verify_no_keys.py`）。

## 四、第三方服务

- AI 能力由**您自行配置**的模型服务商提供（如 DeepSeek、智谱 BigModel、阿里云
  百炼、火山引擎等）。当您发起对话时，提示词、上下文和必要的工具结果会发送到
  您选择的服务商，数据处理遵循该服务商的条款与隐私政策。本应用不是这些服务商
  的代理，也不额外留存请求内容。
- 本应用聚合分发若干开源组件（dsh、dsh-TUI、xterm.js、tmux、Node.js 等，均为
  MIT/ISC 等宽松许可），清单与版权人见
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。这些组件在本机运行，不向
  运营者回传数据。
- dsh 上游版本可能包含匿名产品分析/遥测开关（取决于版本与您的配置）。本应用
  不额外开启、不转发此类数据；如需完全关闭，请在 dsh 配置中禁用相关插件。
- 本应用与 DeepSeek 官方无隶属关系；“DeepSeek”“DeepSeek Harness”“dsh” 是
  DeepSeek 的项目/品牌名称，MIT 许可证不包含商标授权。

## 五、网络访问

本应用会访问：① 您配置的模型服务商 API；② npm 镜像 / 软件源（仅在构建镜像或
执行「升级 dsh」时）；③ 您通过 dsh 工具主动访问的网站或服务；④ 您配置的代理
（如有）。除此之外不主动外联。

局域网访问默认无鉴权；通过 UGREENlink 等远程方式访问时，请设置访问口令，并
妥善保管模型 API Key。

## 六、数据的存储、删除与导出

- 全部数据位于您安装时指定的 `DATA_PATH`，由您完全掌控；可在文件管理器中
  直接查看、备份、删除。
- 删除数据：删除 `DATA_PATH` 目录即可（或先卸载应用再删除该目录）；删除后
  不可恢复。
- 导出数据：直接复制 `DATA_PATH` 目录，或使用 dsh 自身的会话导出功能。
- 运营者不持有您的任何数据副本，因此无法代为导出或删除。

## 七、未成年人保护

本应用面向具备 NAS 运维能力的成年用户，适用年龄为 **18 周岁及以上**；不面向
未成年人设计，也不主动收集未成年人信息。

## 八、您的权利

您对上述信息享有知情、查阅、复制、更正、删除的权利。由于数据全部存放在您
自己的设备上，这些权利可直接通过文件系统与 dsh 界面行使；如对本政策有疑问，
可通过第九节方式联系运营者，我们将在 15 个工作日内答复。

## 九、政策更新与联系方式

- 本政策更新时，会同步修改本文件顶部的版本号与生效日期，并在应用内展示最新
  版本；重大变更会在应用内显著提示。
- 联系方式：menglong_yuan@126.com ／
  <https://github.com/firewelly/nasdsh/issues>

<!-- lang:zh:end -->

<!-- lang:en:begin -->

## 1. Who operates this app

- **App**: NasDSH Workbench (bundles DeepSeek Harness)
- **App ID**: `com.firewell.nasdsh`
- **Operator**: Menglong Yuan (袁梦龙), individual developer — no company, no
  registered business premises
- **Privacy contact**: Menglong Yuan, menglong_yuan@126.com
- **Support**: <https://github.com/firewelly/nasdsh/issues>
- **Nature of service**: a local tool running on your own NAS; free, no in-app
  purchases, no ads

## 2. What we do NOT collect

- There is **no operator-side server**. We do not upload, collect or analyse your
  project files, prompts, conversations, code, terminal output or personal data.
- No ad SDKs, profiling, behavioural tracking or third-party analytics SDKs.
- No account system, and no device permissions (camera, contacts, location,
  microphone, SMS, etc.) are requested.

## 3. Disclosure by feature

The app processes the following information only when you actively use the
corresponding feature, and **all of it stays in the data directory you chose on
your own NAS** (`DATA_PATH`). None of it is sent to the operator. Item 4 is a
request to a provider *you* configure, not a transfer to the operator.

| # | Feature | Data | Purpose | How it is handled | Storage / retention |
|---|---|---|---|---|---|
| 1 | Access PIN (optional) | The PIN you set (`TERMINAL_PIN`) | Authenticate visitors so others on the LAN/remote cannot open the workbench | Passed in at install time, written to a private file, then removed from the process environment. Login uses challenge-response: the browser submits only `sha256(nonce + sha256(PIN))`; the plaintext PIN never leaves the browser, never appears in a URL and is never logged. The server keeps only a digest for comparison | `DATA_PATH/.term_pin` (mode 0600). Not collected if you leave the parameter empty; deleted when you disable the PIN or remove the file |
| 2 | AI model calls | The model API key you enter | Let dsh call the model provider you choose | Entered by you in the dsh UI or config; used only to call that provider | `DATA_PATH` (dsh credential store, mode 0600); removable in dsh settings |
| 3 | Sessions & workspaces | Session records, workspace paths, UI settings, runtime logs | Keep sessions alive across window closes; troubleshooting | Read/written locally by dsh / dsh-TUI | `DATA_PATH/dsh-home`, `DATA_PATH/home`, `DATA_PATH/logs`; until you delete them |
| 4 | Model conversations | Prompts, context, tool results | Complete the conversation you started | Sent by the container directly to the endpoint **you** configured; the app does not proxy, relay or additionally retain them | Not retained by the app; provider-side handling follows that provider's terms |
| 5 | Outbound proxy (optional) | Proxy address, trusted hosts (`proxy.env`) | Route container traffic through your proxy, or allow extra hosts | Read locally; exported into the container process environment | `DATA_PATH/proxy.env`; deleted with the file |
| 6 | Plugins / MCP connectors (optional) | Config of dsh plugins you install | Extend dsh capabilities | Executed locally by dsh; network use depends on the plugin you install | `DATA_PATH/dsh-home/profiles`; removed with the plugin |

**No credentials are preloaded**: neither the repository nor the image contains any
API key, PIN or account data; the build pipeline scans every image layer
(`tools/verify_no_keys.py`).

## 4. Third parties

- AI capability comes from the model provider **you** configure (e.g. DeepSeek,
  Zhipu BigModel, Alibaba Bailian, Volcano Engine). Your prompts, context and
  necessary tool results are sent to that provider under its own terms.
- The app aggregates open-source components (dsh, dsh-TUI, xterm.js, tmux,
  Node.js; MIT/ISC and similar permissive licences). See
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the list and copyright
  holders. They run locally and send nothing to the operator.
- Upstream dsh may include an anonymous-telemetry switch depending on version and
  your configuration. This app neither enables nor forwards such data; disable the
  relevant plugin in dsh to turn it off completely.
- This is not an official DeepSeek product. "DeepSeek", "DeepSeek Harness" and
  "dsh" are DeepSeek's project/brand names; the MIT licence grants no trademark
  rights.

## 5. Network access

The app contacts: (1) the model provider API you configure; (2) npm mirrors /
package registries, only when building the image or running "Upgrade dsh";
(3) sites or services you access through dsh tools; (4) your proxy, if configured.
It makes no other outbound connections.

LAN access is unauthenticated by default. When exposing the app remotely
(e.g. via UGREENlink), set an access PIN and keep your model API keys safe.

## 6. Storage, deletion and export

- All data lives in the `DATA_PATH` you chose and is fully under your control.
- Delete: remove the `DATA_PATH` directory (or uninstall the app first, then
  delete it). Deletion is irreversible.
- Export: copy `DATA_PATH`, or use dsh's own session export.
- The operator holds no copy of your data and therefore cannot export or delete
  it on your behalf.

## 7. Children

The app targets adult users who administer a NAS; minimum age **18**. It is not
designed for minors and does not knowingly collect their data.

## 8. Your rights

You may request information about, access, copy, correct or delete the data
described above. Because all data is on your own device, these rights are
exercised directly through the file system and the dsh UI. Questions about this
policy: see section 9; we reply within 15 business days.

## 9. Changes and contact

- Updates change the version and effective date at the top of this file and are
  shown in-app; material changes are highlighted in the app.
- Contact: menglong_yuan@126.com /
  <https://github.com/firewelly/nasdsh/issues>

<!-- lang:en:end -->
