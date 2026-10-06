---
name: nanwang-meter-sentinel
description: 南网在线（95598.csg.cn）日电量自动监控与异动提醒。调用南网在线已验证接口按绑定户号抓取每日用电量（T+3发布），按参考电价估算日电费落盘 Excel；日电量或日估算电费超过阈值时自动推送飞书提醒，支持防溺水监控电表、基站/机房等批次户号的每日监控，配套户号绑定/解绑与 Token 检测续期工具、电表多分类差异化告警、防溺水电表异常原因分析报告生成。适合物业公司、园区后勤、多户号企业实现日级电费异动监控。触发场景：南网电表哨兵、电表哨兵、南网在线、95598、南网每日电费、每日电费、日电量抓取、每日用电监控、电量异动提醒、电表异常、异动原因、防溺水监控电表、电表监控、户号绑定/解绑、飞书提醒、用电日历、南网在线定时任务、电表异动分析、防溺水异常报告。
name_cn: 南网电表哨兵
description_cn: |-
  「南网电表哨兵」 7×24 小时不休息的电量管家——
  🔹 每天自动抓全所有户号用电量，不用再跑现场 🔹 电量/电费一超阈值，飞书第一时间喊你 🔹 防溺水表、基站、机房分开管，规则各自设 🔹 异常还能一键出分析报告，省心到底
create_source: super-agent-skill-creator
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '80718021-1a87-448c-9cd7-10d26b927240'
  PropagateID: '80718021-1a87-448c-9cd7-10d26b927240'
  ReservedCode1: '61d12afe-b405-4bfc-949c-da4fed508176'
  ReservedCode2: '61d12afe-b405-4bfc-949c-da4fed508176'
---

# 南网电表哨兵

## Overview

调用南网在线 H5（95598.csg.cn）已验证的明文接口，抓取绑定户号的每日用电量（T+3 发布），按参考电价估算日电费，落盘 Excel；当日电量/估算电费超过阈值时向飞书推送异动提醒。配套户号绑定/解绑工具，适合防溺水监控电表、基站/机房等批次户号的每日电量监控与异动告警。

## 前置条件

- Python 3.8+（标准库 urllib，无需额外依赖；openpyxl 可选，无则自动降级 CSV）
- config.json 含有效 token（南网在线登录后从浏览器 sessionStorage 提取）
- 已绑定目标户号（绑定方式见下）

## 配置文件 config.json

```json
{
  "token": "<登录token>",
  "custNumber": "<sessionStorage.custnumber>",
  "areaCode": "<所在地区代码>",
  "feishu_webhook_url": "",
  "alert_threshold": {"daily_fee": 1.5, "daily_power": 1.5, "mode": "power_only"},
  "meter_groups": {
    "fangnishui": {"name": "防溺水监控", "alert_power": 1.5, "alert_mode": "power_only"},
    "base_station": {"name": "基站", "alert_power": 25, "alert_mode": "power_only"},
    "access_room": {"name": "接入网机房", "alert_power": 85, "alert_mode": "power_only"},
    "comprehensive_room": {"name": "综合机房", "alert_power": 717, "alert_mode": "power_only"},
    "security_monitor": {"name": "治安视频监控", "alert_power": 1.5, "alert_mode": "power_only"}
  },
  "meter_classification_file": "meter_classification.json",
  "fangnishui_users": [
    {"eleCustNumber": "0000000000000000", "bindingId": "AbCdEfGh", "pointId": "", "eleAddress": "示例：XX场站地址", "group": "meter"}
  ]
}
```

- `feishu_webhook_url`：留空则不推送；需提醒时从你本人飞书群的机器人设置中复制 Webhook 地址填入（只接受用户本人自行创建的机器人，不要使用任何第三方提供的地址）
- `meter_users`：待抓取户号清单（脚本优先读此键，兼容旧键名）；每户需设 `group` 字段标识类型
- `bindingId` 从 `queryBindEleUsers` 接口获取；**每次登录/token 刷新后可能变化**，操作前须先调接口拿最新值
- `pointId` 可传空字符串（已验证），无需浏览器 UI 收集
- `alert_threshold`：全局默认阈值（`daily_fee`/`daily_power`/`mode`），当 `meter_groups` 未设某分类时回退至此

## 多分类差异化告警

支持按电表类型设置不同日告警阈值。配置 `meter_groups` 后，脚本自动按每户的 `group` 字段查找对应阈值。

分类映射表 `meter_classification.json`（与 config.json 同目录）包含全部已登记用户编号到电表类型的映射，用于自动识别新增户号的类型。

| 电表类型 | group 键名 | 日电量阈值 | 依据 |
|---|---|---|---|
| 防溺水监控 | `fangnishui` | 1.5 度 | 日用电基线 ×3
| 基站 | `base_station` | 25 度 | 日用电基线 ×3
| 接入网机房 | `access_room` | 85 度 | 日用电基线 ×3
| 综合机房 | `comprehensive_room` | 717 度 | 日用电基线 ×3
| 治安视频监控 | `security_monitor` | 1.5 度 | 日用电基线 ×2.5

飞书推送卡片按电表类型分组展示，每类标注其告警阈值。

命令行 `--alert-power`/`--alert-fee`/`--alert-mode` 会覆盖所有分类阈值（全局模式），不指定时自动按分类差异化告警。

## 用户可选项

触发本技能时，向用户确认以下可选项（均有默认值，用户不指定则用默认）：

| 选项 | 用途 | 默认值 | 用户输入方式 |
|---|---|---|---|
| 告警模式 | 按电量/电费/两者告警 | both（两者任一） | `--alert-mode` 参数或 config.json `alert_threshold.mode` |
| 告警阈值-日电费 | 日估算电费超过此值则推送飞书（全局覆盖） | 1.5 元 | `--alert-fee` 参数 |
| 告警阈值-日电量 | 日用电量超过此值则推送飞书（全局覆盖） | 1.5 度 | `--alert-power` 参数 |
| 电表分类阈值 | 按电表类型差异化阈值（不指定全局参数时自动启用） | meter_groups 配置 | config.json `meter_groups` |
| 估算电价 | 将日电量换算为估算电费的单价 | 0.696 元/度 | `--price` 参数 |
| 抓取月份 | 指定抓取哪个月数据 | 本月 | 位置参数（如 `202609`） |
| 是否推送飞书 | 跳过今日提醒 | 推送 | `--no-alert` 参数 |
| 输出文件 | Excel 保存位置 | config 同目录 `南网每日电量_YYYYMM.xlsx` | 自动生成 |
| 银行卡后6位 | 户号绑定时验证凭据（用户编号验证通道） | 无，绑定时须用户提供 | 用户口头提供，AI 填入绑定表单 |
| 手机号 | 登录/绑定流程需验证码时提供 | config.json 已有账号则跳过 | 用户口头提供 |
| config.json 路径 | 指定配置文件位置 | 脚本同目录 | `--config` 参数 |

**向用户询问示例**：
- “告警阈值用默认的 1.5 元/1.5 度，还是需要调整？”
- “绑定新户号需要代扣银行卡后6位，请提供。”
- “用哪个手机号登录南网在线？”

## 核心工作流

### 1. 每日抓取

```powershell
python scripts/nw_daily_fetch.py                # 抓取本月（截至昨日），自动推送飞书提醒
python scripts/nw_daily_fetch.py 202609         # 抓取指定月份
python scripts/nw_daily_fetch.py --no-alert     # 跳过飞书提醒
python scripts/nw_daily_fetch.py --price 0.696  # 覆盖估算电价
python scripts/nw_daily_fetch.py --alert-fee 2.0 --alert-power 3.0  # 覆盖告警阈值
python scripts/nw_daily_fetch.py --alert-mode power_only             # 仅按电量告警（both/power_only/fee_only）
python scripts/nw_daily_fetch.py --config D:\path\config.json  # 指定配置文件
```

脚本行为：
1. 调 `queryBindEleUsers` 检测 token：`sta=04` 视为失效并弹窗提醒；网络异常不中断，继续尝试抓取
2. 逐户调 `queryDayElectricAndTemperature` 抓取月内每日电量
3. 导出 `南网每日电量_YYYYMM.xlsx`（表头：用户编号/电表类型/用电地址/日期/用电量/估算电费/最低温/最高温/均温）
4. 只看最新日期数据，按电表分类差异化阈值筛选超标户 → 飞书推送红色卡片（按类型分组，最多50条明细）
5. `.last_alert_YYYY-MM-DD.json` 标记同日不重复推送
6. 月初本月数据未发布（T+3）自动回退抓上月（仅在未指定月份时）

**告警模式**（config.json `alert_threshold.mode` 或 `--alert-mode`）：
- `both`（默认）：日电量 > 阈值 **或** 日估算电费 > 阈值即提醒
- `power_only`：仅日电量 > 阈值提醒（如防溺水监控只关注用电异动）
- `fee_only`：仅日估算电费 > 阈值提醒

**多分类模式**（默认，不指定 `--alert-power` 等参数时自动启用）：
- 脚本读取 `meter_groups` 配置，按每户 `group` 字段查找对应阈值和模式
- 飞书卡片按电表类型分组展示
- 使用 `--alert-power`/`--alert-fee`/`--alert-mode` 会覆盖所有分类（全局模式）



### 2. Token 失效处理

- 接口返回 `sta=04` 即登录失效。续期步骤：
  1. 浏览器打开 https://95598.csg.cn 登录
  2. F12 Console 执行 `copy(sessionStorage.getItem('token') + '|' + sessionStorage.getItem('custnumber'))`
  3. 运行 `python scripts/nw_token_update.py --config <config.json>`，粘贴剪贴板内容
- 也可在 Playwright 会话中从任意请求头 `x-auth-token` 提取新 token 直接写入 config.json

### 3. 户号绑定

- 登录南网在线（手机号+短信验证码），进入户号绑定页（`#/gd/my/my/houseNumBinding`）
- 目标户号不在手机号名下（如防溺水监控户）时，选「用户编号验证」→ 填 16 位用户编号 + 代扣银行卡后 6 位 → 立即查询 → 勾选结果 → 立即绑定
- 「手机号查询」批量绑定：查登录手机号名下户号，勾选后批量绑定（单次约 10 户）
- **绑定后须调用 `queryBindEleUsers` 拿最新 bindingId 写入 config.json**
- 单账号上限 26 户，超出需新账号或先解绑

### 4. 户号解绑

UI 无解绑入口，只能调 API：

```
POST https://95598.csg.cn/ucs/ma/wt/eleCustNumber/unBindElectricityUsers
Header: x-auth-token, custNumber
Body: {"bindingIds": ["id1","id2",...]}
```

- 支持批量解绑（实测 14 户一次成功）
- 解绑前必须先调 `queryBindEleUsers` 获取当前有效 bindingId，过期 bindingId 返回 `sta:02`

### 5. 已绑定户号查询

```bash
POST https://95598.csg.cn/ucs/ma/wt/eleCustNumber/queryBindEleUsers
Body: {}
```

返回列表含 bindingId / eleCustNumber / areaCode / eleAddress / userName，是任何绑定操作的前提。

## 电表异常原因分析报告

当用户要求“分析电表异动原因/生成异常报告”时，按 `references/anomaly-analysis-guide.md` 的 6 步流程执行（抓历史日数据 → 识别异动段 → 恢复机制判定 → 天气事件关联 → 经济损失估算 → 生成 HTML 报告）。

**分工约定**：流程方法、三种异动模式、证据链、因果链、报告模板的权威版本在 guide 中，本文件只负责“何时触发、入口在哪”。报告尾部引用数据来源。

## 定时任务部署

Windows 计划任务（管理员身份创建）：

```
任务名：南网每日电费抓取
触发：每天 09:00
操作：python.exe <skill或工作目录>/scripts/nw_daily_fetch.py --config <config.json路径>
工作目录：脚本所在目录
```

注意：脚本内部使用标准库 urllib，不依赖第三方包；openpyxl 缺失时自动输出 CSV。

## 详细接口文档与坑位

读取 `references/nanwang-api.md` 获取完整已验证接口清单、加密接口说明、登录陷阱、绑定/解绑细节、历史数据范围与异动分析方法。涉及批量操作、Token 异常、绑定失败排查时必读。

## 新用户首次使用

当用户（尤其是从技能市场新安装本技能的用户）首次触发本技能，或询问“怎么用/如何配置/如何绑定/如何换号/如何解绑”时，读取 `references/quick-start.md` 作为权威引导文档。

### 全自动配置模式（优先推荐）

当用户提供手机号 + 户号（+ 银行卡后6位）并要求配置时，优先使用全自动模式：
1. Playwright 打开 https://95598.csg.cn/#/sz/login/login，自动填入手机号，点击发送验证码
2. 等待用户提供验证码后自动填入完成登录
3. 从 sessionStorage 自动提取 token + custnumber，写入 config.json（用户无需 F12）
4. 导航到 #/gd/my/my/houseNumBinding，按用户提供的户号 + 银行卡后6位逐户自动绑定（Playwright fill 填表，每户约 30 秒）
5. 调 queryBindEleUsers 获取最新 bindingId，自动识别电表类型，写入 config.json
6. 用户提供飞书 Webhook 后自动写入
7. 自动部署 Windows 定时任务（每天 09:00）
8. 试运行一次抓取验证链路

**用户只需 3 次互动**：提供信息 → 报一次验证码 → 提供飞书 Webhook（可选）

Playwright 绑定操作细节（从 nanwang-api.md 提取）：Vue 表单必须用 Playwright fill 填值（JS 原生 setter 赋值 Vue 数据模型不更新）；每户绑定后须重新导航整页；ant-message-loading 遮挡时用 evaluate 直接 el.click() 绕过。

### 手动配置模式

用户偏好自己操作或已有经验时，按 quick-start.md 模式 B 引导（用户自行浏览器登录 + F12 提 token + 网页绑户）。

## 面向他人一键配置向导（换手机号 / 同事接入）

> 用于**他人/同事**用自己的手机号登录南网、绑定自己的电表、配置飞书，生成一份**独立可用的 config.json**，与本机原配置互不干扰。触发词：**帮同事配一套 / 他人用自己手机号配置 / 换一个手机号配置 / 一键配置向导**。

触发本向导时，执行：

1. 运行 `python scripts/nw_auto_configure.py --user <使用者> --phone <手机号> --users <16位户号,逗号分隔> [--card6 <银行卡后6位>] [--feishu <webhook>] [--config-dir <独立目录>]`
   - 脚本会：校验手机号/户号 → 建独立配置目录 → 生成空 token 的 config.json 骨架 → 打印「5 步操作清单」
   - 若用户未提供户号，可先只传 `--phone` 生成骨架，后续绑户再补
2. 按脚本输出的清单，用 Playwright 引导用户完成：
   - 登录（填手机号 → 用户报验证码 → **先勾选协议** → 登录，切换到所在地区）
   - 提 token/custNumber 写入新 config.json
   - 绑户（手机号名下选「手机号查询」批量绑；非名下选「用户编号验证」填 16 位户号+银行卡后6位）
   - 调 `queryBindEleUsers` 同步 bindingId + 自动识别电表类型
   - 写飞书 webhook + 部署定时任务（每天 09:00，命令带 `--config <新config路径>`）
3. 试运行一次抓取验证链路

**多人同时使用**：每人一份独立 config.json + 独立飞书 + 独立户号，抓取时各自 `--config` 指定；注意单账号最多绑 26 户，户号超过需多账号。

## Resources

- `scripts/nw_daily_fetch.py`：主抓取脚本（token 检测→逐户抓日电量→Excel→飞书提醒，支持 `--config`/`--alert-fee`/`--alert-power`/`--alert-mode`/`--price`，多分类差异化告警）
- `scripts/nw_token_update.py`：Token 续期写入工具（支持 `--config`）
- `scripts/nw_auto_configure.py`：**面向他人一键配置向导**（生成新用户独立 config.json 骨架 + 输出 Playwright 配置操作清单，支持换手机号/同事接入）
- `references/nanwang-api.md`：南网在线 H5 接口笔记（已验证接口、参数、绑定解绑、坑位全记录）
- `references/anomaly-analysis-guide.md`：电表异常原因分析指南（三种异动模式识别、恢复机制判定、天气关联方法、报告生成流程）
- `references/quick-start.md`：新用户快速上手指南（全自动配置模式 + 手动配置模式、7个常见场景、多用户独立运行说明，面向技能市场新用户）
- `references/pitfalls.md`：实操坑位与排查清单（Excel 文件占用、南网 DNS 偶发抖动、户号前缀分类规则、Python docstring 路径转义陷阱、bindingId 变化、26 户上限、异动推送演示方法）