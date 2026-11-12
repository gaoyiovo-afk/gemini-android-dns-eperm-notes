# Android Gemini 网络错误：GMS DNS EPERM 排障记录

2026-11-12，在一台运行 Android 16 的荣耀设备上，Gemini Android 应用持续显示“连接已中断……(4)”。Clash Meta 的 VPN 已开启，普通连通性测试能够访问 Google，但 Google Play 服务获取凭证时仍报 `ERR_NAME_NOT_RESOLVED (-105)`。

**有效绕行设置：Clash Meta for Android → 设置 → 网络 → 打开“系统代理”，随后重新连接。** 该选项的界面说明是“为 VpnService 附加 HTTP 代理”。本例恢复了 Google 认证、Gemini 服务端资格检查及对话首页加载。

进一步采集 Android 系统 DNS 事件，发现 Google Play 服务对应的 **7 次采样解析调用中，49 次查询尝试全部记录了 `EPERM`**，随后解析接口返回 `EAI_NODATA`。`EPERM` 是本机网络操作的错误，不能解释为 DNS 服务器返回了“权限不足”。

这是单台设备的排障案例。**已定位到 DNS 网络操作遭权限拒绝，尚未定位作出拒绝决定的具体系统调用、规则或组件。** 这里不作厂商或项目的最终归因，也不保证同样设置能解决所有 Gemini 网络错误。

## 快速处理步骤

1. 确认问题与本例相似：VPN 已连接，Google Play 服务日志反复出现 `ERR_NAME_NOT_RESOLVED`、获取令牌的 `NetworkError`。
2. 在 Clash 主界面停止连接。
3. 进入 **设置 → 网络**，开启 **系统代理**。
4. 回到主界面重新连接，再打开 Gemini。

本例最终保留这个开关。测试用的 Android 全局 HTTP 代理已显式清理并恢复原设置；DNS 增强模式覆写恢复为“不修改”，网络模式恢复为原来的 Mixed Stack。

撤销本例设置：停止 Clash，关闭“系统代理”，再重新连接。仓库没有提供自动修改手机配置的脚本。

## 环境

| 项目 | 本例环境 |
| --- | --- |
| 设备 | 一台荣耀手机，未 root |
| Android | 16，API 36 |
| Clash Meta for Android | 2.11.7.Meta |
| Google Play 服务 | 26.40.32 (260400-995630914) |
| Google 应用 | 17.72.17.ve.arm64 |
| 上网方式 | 移动数据，Clash VpnService，规则模式 |
| 原网络选项 | Mixed Stack、DNS 劫持开启、IPv6 关闭、允许所有应用、应用绕过关闭 |
| 系统私人 DNS | 关闭 |

设备序列号、账户、订阅、代理提供商、节点、实际 DNS 服务器地址、设备网络地址和本地路径均未收录。

## 实验结果

| 对照 | 结果 |
| --- | --- |
| 只重开 Google 应用 / Gemini | 未解决 |
| 重启 Google Play 服务 | 未解决 |
| 临时换用真实 IP 解析 | 未解决，已恢复 |
| 无 HTTP 代理，Mixed Stack | 系统 DNS / Cronet 错误可复现 |
| 无 HTTP 代理，System Stack | 同样可复现，已恢复 |
| 无 HTTP 代理，Chrome 访问同一认证端点 | 收到服务器的 HTTP 405；已连通，GET 方法不适用于该认证接口 |
| ADB 下直接进行 UDP / TCP DNS 查询 | 正常返回地址 |
| ADB 身份调用 Android 默认解析 / 指定 VPN 解析 | 均成功 |
| 显式 HTTP 代理 | 认证与 Gemini 首页恢复 |
| 清理全局代理残留后，仅保留 VPN 附加代理 | 仍然成功 |

系统统计的核心结果：

| 字段 | 观察值 |
| --- | --- |
| 采样到的解析调用 | 7 次，不代表总调用数 |
| 解析入口 | `getaddrinfo` |
| 系统返回码 | 7 次均为 `EAI_NODATA` |
| 查询尝试 | 49 次，全部 `linux_errno = 1 (EPERM)` |
| 查询类型 | 48 条 A，1 条 AAAA |
| 传输 | UDP |
| 网络 | 6 次移动网络叠加 VPN，1 次移动网络 |
| 整次解析耗时 | 1.288—3.975 毫秒 |

完整分析见 [CASE_STUDY.md](CASE_STUDY.md)。统计投影见 [脱敏 DNS 事件](evidence/dns-events.sanitized.json)；字段说明见 [evidence/README.md](evidence/README.md)。

## 机制与结论边界

故障复现期间，同一应用身份及同一时间窗口的系统 DNS 事件和上层日志支持以下链条：

```text
DNS 套接字操作记录 EPERM
  → getaddrinfo 返回 EAI_NODATA
  → Cronet 报 ERR_NAME_NOT_RESOLVED
  → 上层显示网络错误
```

附加 HTTP 代理后，客户端可把目标域名交给代理链路处理，从而避开本例失败的目标域名 DNS 操作。Clash 使用 Android 的 `VpnService.Builder.setHttpProxy` 为 VPN 网络设置代理。

已读取的 AOSP BPF 表显示，该应用有联网权限、对应后台允许位，局域网禁止名单为空。这些可见规则尚未解释 `EPERM`。还未取得目标进程内系统调用跟踪，不能断言具体是 `bind`、`setsockopt`、`connect`、`send` 或其他操作被拒绝，也不能锁定某一厂商、应用或项目。

DNS 统计不含域名，不能将每个底层样本与某个认证 URL 逐条对应。账户与资格缓存还可能让首页继续显示正常，因此仅观察首页不足以判断底层 DNS 已恢复。

## 实验中纠正的一处陷阱

**删除 Android 全局代理的设置键，不一定清除了内存里的代理状态。** 本例曾因此得到一轮无效的“关闭代理后仍成功”结果。

后续先显式执行 `settings put global http_proxy :0` 清除内存状态，再恢复原设置，并核对实际 `PROXY_CHANGE` 广播和 VPN 网络属性。这里收录的无代理基线、System Stack 对照及底层采样，均在清理残留后进行。详见 [调查记录](CASE_STUDY.md#一项已纠正的实验条件)。

## 离线检查证据

仓库里的 Python 脚本只读取本地 JSON 并统计，不连接 ADB、不联网、不改手机：

```console
python tools/summarize_dns_events.py
```

输出应与 [evidence/summary.json](evidence/summary.json) 一致。该检查只能验证收录数据与统计相符，不能独立证明现场采集过程。

## 参考实现

- [Android 16 DNS 查询实现：res_send.cpp](https://android.googlesource.com/platform/packages/modules/DnsResolver/+/refs/tags/android-security-16.0.0_r1/res_send.cpp)
- [系统 DNS 事件及错误码定义](https://android.googlesource.com/platform/packages/modules/DnsResolver/+/6439138175af48d4739605676f865b6906678fdc/stats.proto)
- [Android VpnService.Builder.setHttpProxy](https://developer.android.com/reference/android/net/VpnService.Builder#setHttpProxy(android.net.ProxyInfo))
- [Clash Meta 的 VPN / 系统代理实现](https://github.com/MetaCubeX/ClashMetaForAndroid/blob/main/service/src/main/java/com/github/kr328/clash/service/TunService.kt#L186)
- [AOSP ProxyTracker 镜像](https://github.com/msft-mirror-aosp/platform.packages.modules.Connectivity/blob/main/service/src/com/android/server/connectivity/ProxyTracker.java)

本仓库保存经过筛选的调查文档与统计投影。原始 logcat、界面 XML、完整网络转储、临时 DEX、账号和代理配置不属于仓库内容。
