# Gemini 网络错误：底层故障定位

记录日期：2026-11-12。设备及账户标识已省略。

## 已确认的故障点

故障复现期间，Android 系统解析器为 Google Play 服务记录的 DNS 网络操作出现 **Linux `EPERM`（不允许该操作）**，最终系统 `getaddrinfo` 返回 `EAI_NODATA`，Google 的 Cronet 网络组件再向上报告 `ERR_NAME_NOT_RESOLVED (-105)`。

这一轮已经获得操作系统 DNS 诊断数据，结论比“Google 的解析路径有问题”更具体。现有数据支持将直接失败点定位到 **Google Play 服务身份下的 DNS 套接字操作权限拒绝**，还不能确定具体由哪一个系统调用、哪条过滤规则或哪个组件造成。

## 核心证据

使用 Android statsd 的 `NetworkDnsEventReported`（atom 116）临时收集系统 DNS 事件，并以 ADB 身份的受控解析失败及诊断标记验证采集通道确实在工作。该事件不记录域名或用户聊天内容。

只统计 Google Play 服务对应的专用 metric，避免把同时记录在汇总 metric 中的事件重复计算。仓库数据已删除实际 UID 和采集 metric 编号：

| 字段 | 实际观察 |
| --- | --- |
| 采样到的系统 DNS 调用 | 7 次；这是采样结果，不能当作总调用数 |
| 调用入口 | `EVENT_GETADDRINFO` |
| 系统返回码 | 7 次均为 `RC_EAI_NODATA = 7` |
| 调用 flags | `1024`，即 `AI_ADDRCONFIG` |
| 查询尝试记录 | 共 49 条，全部 `linux_errno = 1`，即 `EPERM` |
| DNS 查询类型 | 48 条 A，1 条 AAAA |
| DNS 传输 | UDP |
| DNS 查询结果字段 | 49 条均为内部错误值 254，没有普通有效 DNS 应答 |
| 网络类型 | 6 次移动网络叠加 VPN；1 次移动网络 |
| 整次解析耗时 | 约 1.288—3.975 毫秒 |

同一采样窗口的 Google 日志中出现了 53 处 `ERR_NAME_NOT_RESOLVED`。堆栈会重复打印同一个错误，这个数值不能解释为 53 个独立请求。

套接字元数据采样还观察到一个归属该 UID、目标为 DNS 服务器 53 端口的 UDP 套接字。不过，现有事件没有将每一条报错与某个具体文件描述符对应，因此不能据此进一步断言所有拒绝都发生在 `send()` 而非其他套接字操作上。

## 调用链的解释

```text
Gemini / Google 应用需要联网或获取凭证
  → Google Play 服务使用系统 DNS 解析
  → DNS 网络操作记录 EPERM
  → getaddrinfo 返回 EAI_NODATA
  → Cronet 返回 ERR_NAME_NOT_RESOLVED
  → 上层显示网络错误
```

Android DNS 实现将每次查询的系统错误记录到 `DnsQueryEvent.linux_errno`，并专门把 `EPERM` 视为网络操作可能受限的情况。UDP 路径涉及创建套接字、打标记、设置网络标记、绑定、连接、发送与接收等步骤。现有 atom 记录保留了结果，但没有指出其中哪个系统调用返回了拒绝。

代码依据：[Android 16 DNS 查询实现](https://android.googlesource.com/platform/packages/modules/DnsResolver/+/refs/tags/android-security-16.0.0_r1/res_send.cpp)、[系统 DNS 事件及错误码定义](https://android.googlesource.com/platform/packages/modules/DnsResolver/+/6439138175af48d4739605676f865b6906678fdc/stats.proto)。

## 对照排查结果

| 对照 | 结果及意义 |
| --- | --- |
| ADB 的普通 HTTPS 测试 | Google 认证与 Gemini 公开端点可以完成连接；无法据此代表 Google Play 服务身份下的网络权限 |
| 直接向 VPN DNS 发 UDP、TCP 查询 | 均能正常返回 A 记录；不支持“DNS 服务器整体不工作”的解释 |
| Android `InetAddress.getAllByName` | ADB 身份下解析正常 |
| Android `Network.getAllByName`，指定当前 VPN | ADB 身份下解析正常；显式按 VPN 网络解析的接口并未普遍失效 |
| Chrome，在确认没有 HTTP 代理时打开相同认证端点 | 正常收到 HTTP 405，说明已到达服务器；405 是 GET 方法不被该认证接口接受，不是连接失败 |
| Mixed Stack，无显式代理 | 重新启动 Google 服务后仍出现解析错误 |
| System Stack，无显式代理 | 同样出现解析错误；仅切换此模式未解决 |
| 临时使用真实 IP 解析 | 早期测试未恢复；已恢复订阅原来的 DNS 模式 |
| 显式 HTTP 代理 | Google 认证、服务端资格检查及 Gemini 首页加载恢复 |

Android 原生 DNS 两个小探针由本地生成的 844 字节和 1004 字节 DEX 运行，仅调用解析接口，不安装 APK、不调用账户接口。它们使用的是 ADB 身份，不能直接替代 Google Play 服务内部的实验。

## 权限与过滤表检查

通过 `dumpsys connectivity trafficcontroller` 读取到了 AOSP 可见的实际 BPF 表，而不只依赖应用设置界面：

- Google Play 服务有 `PERMISSION_INTERNET` 和 `PERMISSION_UPDATE_DEVICE_STATS`。
- 活跃的 owner match 配置为 `BACKGROUND_MATCH`，该 UID 具有对应允许位；另有计费网络允许标记。
- 数据节省模式关闭。
- `sLocalNetBlockedUidMap` 为空。
- 应用管理中 Google Play 服务的移动数据为允许。

因此，可见的这些表和设置没有给出该 `EPERM` 的直接解释。快照也不能排除瞬时状态、其他内核规则、厂商扩展过滤或套接字网络标记处理等情况；不能从“普通设置允许”直接推导“系统没有任何限制”。

## 一项已纠正的实验条件

早期临时全局代理测试结束时，只删除设置库中的代理键，并检查键值恢复为空。这不足以确认 Android 的内存代理状态已经清除。

后续无代理对照发现，请求仍走本机 HTTP 代理。系统的 `PROXY_CHANGE` 粘性广播也证实，内存中还保留着先前的本机端口。AOSP 的 `ProxyTracker.loadDeprecatedGlobalHttpProxy()` 在设置项为空时不会调用清除代理的方法，这解释了该行为。

现已改为先显式设置 `http_proxy = :0` 清除内存状态，再恢复原来的设置键，并核对实际代理广播与 VPN 的 `HttpProxy` 属性。排障脚本也已修正。

**本报告中的无代理基线、System Stack 对照和底层采样，均在清理该残留后完成。** 首次关闭开关但仍经 HTTP 代理的那轮结果，不能当作无代理对照使用。

源码依据：[AOSP ProxyTracker](https://github.com/msft-mirror-aosp/platform.packages.modules.Connectivity/blob/main/service/src/com/android/server/connectivity/ProxyTracker.java)。

## 为什么附加代理有效

显式 HTTP 代理允许 Google 服务先连接设备上的代理，将目标域名交由代理链路处理，避开原先失败的 Google 服务身份下的目标域名 DNS 操作。Clash 自带开关使用 `VpnService.Builder.setHttpProxy`，将代理附加到 VPN 网络。

在显式清除全局代理残留后，仅保留这个 VPN 附加代理的对照仍然成功。最终工作配置保留“系统代理：开启”，网络处理模式恢复为原来的 Mixed Stack，DNS 增强模式覆写恢复为“不修改”。

## 尚未确定的部分

1. 产生 `EPERM` 的具体系统调用及拒绝规则。
2. 拒绝属于瞬时权限状态、内核过滤、厂商实现还是其他网络路径行为。
3. DNS 事件不含域名，不能把每个底层样本与某个具体认证 URL 一一对应；关联依据是同一 UID、同一复现时间窗口及同步上层日志。

现有非 root 接口没有提供目标进程内的系统调用跟踪，也未给出作出拒绝决定的完整规则。当前可以确认“本机 DNS 操作被权限拒绝”，不能据此给某个厂商、应用或某段代码作最终归因。

## 仓库内证据

- [脱敏系统 DNS 事件](evidence/dns-events.sanitized.json)：仅保留 Google Play 服务专用 metric 的 7 条样本，删除 UID、metric 编号和时间戳。
- [离线统计结果](evidence/summary.json)：由仓库脚本重新计算。
- [字段及脱敏说明](evidence/README.md)：解释采样、查询尝试与调用计数的区别。

原始诊断材料保留在设备所有者本地，不随仓库分发。文中 53 处上层报错、权限表和界面对照来自现场记录；仓库 JSON 本身不包含这些原始日志，读者无法仅凭该文件独立复核所有现场观察。
