# 证据字段与脱敏说明

`dns-events.sanitized.json` 是现场系统 DNS 事件的筛选投影，包含 Google Play 服务对应专用 metric 的 7 条样本。汇总 metric 里重复出现的同一批事件没有再次收录。

已省略：实际应用 UID、采集 metric ID、时间戳、设备和账户标识。没有收录原始 logcat、界面 XML、DNS 服务器地址、套接字端口、订阅配置或本地文件路径。该 DNS atom 本身不含域名。

| 字段 | 含义 |
| --- | --- |
| `sample` | 在本文件中重新编号的样本，不是现场事件 ID |
| `caller` | 概括后的调用方名称，不是原 UID |
| `event_type = 1` | `EVENT_GETADDRINFO` |
| `return_code = 7` | `RC_EAI_NODATA` |
| `latency_us` | 整次解析或单条查询尝试的微秒耗时，取决于所在层级 |
| `hints_ai_flags = 1024` | `AI_ADDRCONFIG` |
| `network_type = 8 / 1` | 移动网络叠加 VPN / 移动网络 |
| `private_dns_mode = 1` | 私人 DNS 关闭 |
| `sampling_rate_denominator` | 该事件的采样率分母；不能将样本数直接当作总量 |
| `queries` | 一次解析中各个 DNS 查询及重试的记录 |
| `record_type = 1 / 28` | A / AAAA |
| `cache_status = 1` | 缓存未命中 |
| `ip_version = 1 / 2` | IPv4 / IPv6 |
| `protocol = 1` | UDP |
| `retry` | 查询的重试序号 |
| `dns_server_index` | 解析器中的服务器序号，不包含服务器地址 |
| `rcode = 254` | 解析器内部错误值；不能当作 DNS 服务器的标准应答码 |
| `linux_errno = 1` | `EPERM`，本机网络操作不被允许 |

`summary.json` 由 `tools/summarize_dns_events.py` 生成。脚本不做采样加权，也不把 49 条查询尝试当作 49 次独立解析。它只检查仓库内数据的算术一致性。

以上枚举参照 [Android 系统 DNS 事件定义](https://android.googlesource.com/platform/packages/modules/DnsResolver/+/6439138175af48d4739605676f865b6906678fdc/stats.proto)。现场系统可能包含厂商改动；这里不据此推断具体责任组件。
