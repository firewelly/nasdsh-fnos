# NasDSH 用户协议（服务条款）/ NasDSH Terms of Service

版本 v1.0 · 生效日期 2026-11-06 · 适用于 NasDSH 工作台 (`com.firewell.nasdsh`)

本协议同时提供中文与英文版本；如有歧义，以中文版本为准。
This agreement is provided in Chinese and English. In case of discrepancy, the Chinese version prevails.

<!-- lang:zh:begin -->

## 1. 服务提供方与平台关系

1. 本应用由 **袁梦龙**（个人开发者，以下简称“我方”）独立开发并提供服务，
   联系方式：menglong_yuan@126.com。
2. 绿联（深圳市绿联科技股份有限公司及其关联公司）仅作为应用市场平台方提供
   展示、分发与技术支持服务，**不是本应用的提供方**，不对本应用的功能、内容
   或效果作出保证。
3. 本应用运行在您自有的 NAS 设备上，我方不提供托管服务，也不接收您的业务数据。

## 2. 服务内容

本应用提供 DeepSeek Harness（dsh）在 NAS 上的工作台外壳：共享 Web 工作台、
每项目一个 CLI 终端（tmux + dsh-TUI）、可选访问口令、会话保持与升级工具。
AI 能力由您自行配置的第三方模型服务商提供，相关费用与条款由您与该服务商约定。

## 3. 使用许可

我方授予您非独占、不可转让的许可，允许您在自有设备上安装、使用本应用。
本应用自研代码以 **MIT 许可证**发布（见 `LICENSE`，版权人
`Copyright (c) 2026 袁梦龙 (Menglong Yuan)`）；随附开源组件遵循其各自许可
（见 `THIRD_PARTY_NOTICES.md`）。MIT 许可不包含商标授权。

## 4. 用户义务

1. 遵守您所在国家/地区的法律法规以及您所用模型服务商的使用条款；
2. 不将本应用用于非法用途，不处理违法内容，不侵害他人合法权益；
3. 对您在终端或 AI Agent 中执行的命令及其后果自行负责——**AI 生成的命令可能
   有误，执行前请自行确认**；
4. 妥善保管访问口令与模型 API Key，不向他人泄露；
5. 不删除或修改本应用随附的版权声明与许可声明。

## 5. 免责声明

1. 本应用按“现状”提供，不附带任何明示或默示担保（包括适销性、特定用途适用性
   与不侵权担保）。
2. 因使用或无法使用本应用导致的任何直接或间接损失（含数据丢失、业务中断、
   模型服务商扣费），在法律允许的最大范围内由您自行承担；建议您自行备份
   `DATA_PATH`。
3. 本应用不提供生成式人工智能服务，仅作为您与所选模型服务商之间的本地客户端；
   AI 输出内容的准确性与合规性由您自行判断并承担责任。
4. 上游 dsh 处于快速迭代阶段，升级可能带来配置或插件兼容性变化。

## 6. 数据与备份

数据全部保存在您指定的 `DATA_PATH`。卸载应用不一定会删除该目录，请自行确认
并备份；删除后不可恢复。

## 7. 服务的变更与终止

1. 我方可能更新本应用或本协议；更新后继续使用即视为接受更新内容。
2. 如本应用停止分发或下架，您已安装的本地版本仍可继续使用（除您主动卸载）；
   我方将尽合理努力提前一个月在项目仓库公告。

## 8. 争议解决

本协议适用中华人民共和国法律。因本协议产生的争议，双方应友好协商；协商不成
的，提交我方所在地有管辖权的人民法院诉讼解决。

## 9. 联系方式

menglong_yuan@126.com ／ <https://github.com/firewelly/nasdsh/issues>

<!-- lang:zh:end -->

<!-- lang:en:begin -->

## 1. Provider and platform relationship

1. This app is developed and provided solely by **Menglong Yuan** (袁梦龙), an
   individual developer ("we"). Contact: menglong_yuan@126.com.
2. UGREEN acts only as the app-market platform (listing, distribution, platform
   support). **It is not the provider of this app** and makes no warranty about
   its functionality, content or results.
3. The app runs on your own NAS. We do not host it and do not receive your data.

## 2. The service

NasDSH is a workbench shell that runs DeepSeek Harness (dsh) on a NAS: a shared
web workbench, one CLI terminal per project (tmux + dsh-TUI), an optional access
PIN, session persistence and an upgrade helper. AI capability is supplied by the
third-party model provider you configure; fees and terms are between you and that
provider.

## 3. Licence

You are granted a non-exclusive, non-transferable licence to install and use the
app on devices you own. Our own code is released under the **MIT licence**
(`LICENSE`, copyright holder `Copyright (c) 2026 袁梦龙 (Menglong Yuan)`).
Bundled open-source components keep their own licences
(`THIRD_PARTY_NOTICES.md`). The MIT licence grants no trademark rights.

## 4. Your obligations

1. Comply with the laws of your jurisdiction and your model provider's terms.
2. Do not use the app for unlawful purposes or to infringe others' rights.
3. You are responsible for commands you run in the terminal or through the AI
   agent — **AI-generated commands can be wrong; review before executing**.
4. Keep your access PIN and API keys confidential.
5. Do not remove copyright or licence notices bundled with the app.

## 5. Disclaimer

1. The app is provided "as is", without warranties of any kind, express or
   implied, including merchantability, fitness for a particular purpose and
   non-infringement.
2. To the maximum extent permitted by law, you bear any direct or indirect loss
   arising from use or inability to use the app (including data loss, downtime or
   provider charges). Back up `DATA_PATH` yourself.
3. The app does not provide generative-AI services; it is a local client between
   you and the provider you choose. You are responsible for judging the accuracy
   and compliance of AI output.
4. Upstream dsh evolves quickly; upgrades may change configuration or plugin
   compatibility.

## 6. Data and backup

All data is stored in the `DATA_PATH` you chose. Uninstalling may not delete that
directory — verify and back it up yourself. Deletion is irreversible.

## 7. Changes and termination

1. We may update the app or these terms; continued use means acceptance.
2. If distribution stops, locally installed copies remain usable (unless you
   uninstall them). We will make reasonable efforts to announce this one month in
   advance in the project repository.

## 8. Governing law

These terms are governed by the laws of the People's Republic of China. Disputes
are resolved by friendly negotiation, failing which by litigation in the competent
court at the provider's location.

## 9. Contact

menglong_yuan@126.com / <https://github.com/firewelly/nasdsh/issues>

<!-- lang:en:end -->
