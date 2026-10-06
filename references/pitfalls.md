---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'a6f14949-57ed-4a52-b634-53b690716606'
  PropagateID: 'a6f14949-57ed-4a52-b634-53b690716606'
  ReservedCode1: '90346532-810d-4955-88f7-d5eb9ad6f63e'
  ReservedCode2: '90346532-810d-4955-88f7-d5eb9ad6f63e'
---

# 南网电表哨兵 - 实操坑位与排查清单

> 本文件汇总实操中反复出现的坑位与对应排查方法，供抓取失败、配置异常、脚本报错时快速定位。按「现象 → 原因 → 处理」组织。

## 1. 输出 Excel 被占用导致保存失败（PermissionError）

**现象**：`nw_daily_fetch.py` 抓取成功，但保存 `南网每日电量_YYYYMM.xlsx` 时报权限错误，脚本中断。

**原因**：该 Excel 正被 Excel/WPS 打开，文件被锁定，脚本无法覆盖写入。特征：目录下存在 `~$南网每日电量_YYYYMM.xlsx` 锁文件。

**处理**：
1. 先检查锁文件：`Test-Path "D:\...\~$南网每日电量_YYYYMM.xlsx"`
2. 请用户关闭 Excel 中打开的文件（有未保存内容先保存），**不要擅自结束 Excel 进程**（可能丢数据）
3. 用户确认关闭后再重跑抓取

## 2. 南网域名 DNS 偶发抖动（getaddrinfo failed / ERR_NAME_NOT_RESOLVED）

**现象**：脚本报 `<urlopen error [Errno 11001/11002] getaddrinfo failed>`，或 Playwright 打开 95598.csg.cn 报 `net::ERR_NAME_NOT_RESOLVED`；但 PowerShell `Test-NetConnection` 测 baidu/qq 都通，仅南网域名解析失败。

**原因**：公司内网 DNS 对 95598.csg.cn 偶发解析失败，属瞬时波动，重试即恢复（非持续断网）。

**排查/处理**：
1. 先区分范围：`Test-NetConnection www.baidu.com -Port 443` 与 `95598.csg.cn` 对比——若仅南网不通，是 DNS 抖动而非整体断网
2. 重试解析：`[System.Net.Dns]::GetHostAddresses("95598.csg.cn")`，通常 1-3 次内恢复
3. 恢复后重跑抓取即可；不要据此判定"南网接口坏了"

## 3. 户号前缀分类规则（防溺水 vs 居民私户）

**现象**：把账号下全部绑定户号写入 `meter_users` 后，居民私户日电量远超 1.5 度阈值，导致误报。

**原因**：同一账号下可能混绑两类户号，需按前缀区分：
- `030820` 开头 → 防溺水监控/基站等**监控户**，纳入抓取与告警
- `03080099` 开头 → **居民私户**（住宅用电），日电量正常即超 1.5 度，**不应纳入监控**，否则误报

**处理**：同步户号时按前缀过滤，只保留 `030820` 开头的监控户；居民户跳过（可保留在账号下但不写入 `meter_users`）。

## 4. Python 脚本 docstring 内嵌 Windows 路径的 Unicode 转义陷阱

**现象**：脚本运行报 `SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes ... truncated \uXXXX escape`，定位在 docstring 第 2 行附近。

**原因**：docstring 示例里写了 Windows 反斜杠路径，如 `D:\user_zhangsan`，其中 `\u` 被 Python 当作 Unicode 转义解析（`\u` 后必须跟 4 个十六进制字符，`user` 不合法 → 报错）。

**处理**：docstring/注释中的路径示例一律用**正斜杠**（`D:/user_zhangsan`）或 `\\` 转义，避免 `\u`、`\n`、`\t` 等被误解析。这是写任何含路径示例的 Python 脚本的通用坑。

## 5. bindingId 每次登录/token 刷新后变化

**现象**：用旧 config 抓取某户报「请确认绑定id是否正确」/ `sta:09 无此用户数据`。

**原因**：`bindingId` 随每次登录/token 变化，config 里的是旧值。

**处理**：任何绑定/解绑/同步操作前，先调 `queryBindEleUsers` 拿最新 bindingId 再写入 config。手抄 bindingId 极易出错（如 `lTBGNzD4` 抄成 `lTvBGNzD4`），尽量用接口返回值程序化写入，避免人工转录。

## 6. 单账号 26 户上限

**现象**：绑户时提示满额，无法新增。

**原因**：单个南网账号最多绑定 26 户（实测确认）。

**处理**：需监控更多户时准备多个账号，或先解绑再绑；一键配置向导对已满账号会跳过新增绑定、直接同步已绑户号。

## 7. 演示/测试「异动推送」：临时调低阈值触发真实飞书推送

**场景**：用户要求「演示异动电表提示功能」，但最新日各户电量均未超阈值（如某月各户正常，最高 1.40 度 < 1.5 度），脚本不会推送，无法演示。

**方法**（在独立演示配置上操作，勿动生产 config）：
1. 删除防重复推送标记 `.last_alert_YYYY-MM-DD.json`（否则脚本认为同日已推送而跳过）
2. 临时把目标分类阈值调低到能触发若干户的值（如监控 1.5 → 1.0，让最新日电量 >1.0 的户触发）
3. 运行 `nw_daily_fetch.py --config <演示config>` 触发真实飞书推送
4. 演示完成后**必须恢复原阈值**（1.5）并清理 `.last_alert` 标记，避免日常误报

**要点**：
- 用独立演示配置（如 `user_<手机号>/config.json`）操作，与生产 config 隔离，互不干扰
- 演示前先读最新日电量分布，选一个能触发 3-5 户的阈值，卡片效果更直观
- 阈值是临时演示手段，恢复是硬性要求；可在 config 加 `_demo` 注释标记，恢复时一并清除