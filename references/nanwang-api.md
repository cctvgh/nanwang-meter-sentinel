---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '40c3403e-50e5-4e89-a979-90711e5786e0'
  PropagateID: '40c3403e-50e5-4e89-a979-90711e5786e0'
  ReservedCode1: '7c0416c2-9926-46c5-82b2-4e3d0981cd39'
  ReservedCode2: '7c0416c2-9926-46c5-82b2-4e3d0981cd39'
---

# 南网在线 H5 每日电费查询接口笔记（公开版）

> 平台（95598.csg.cn）登录闭环、单户查询、自动抓取、飞书提醒均已跑通并支持部署定时任务。户号绑定双通道均已打通：「手机号查询」批量绑定；「用户编号 + 代扣银行卡后 6 位」逐户绑定。单账号绑定上限约 26 户；`meteringPointId` 可传空字符串，无需浏览器 UI 收集。

## 平台与认证机制（已实测确认）

- H5 端：`https://95598.csg.cn`（Vue 单页应用；登录页 `#/sz/login/login`）
- 请求风格：POST + JSON；响应格式 `{"sta":"00","message":"success","data":...}`，`sta="00"` 表示成功，`sta="04"` 表示未登录/token 失效
- 认证头：`x-auth-token`（登录后下发，存储在 `sessionStorage.token`）；另需 `custNumber` 头（值在 `sessionStorage.custnumber`）
- 登录方式：手机号 + 短信验证码（验证码按钮约 120 秒冷却）；登录后 token 存 sessionStorage
- 首页有免登录"电费查询"快捷入口：用户编号 + 预留手机号 + 验证码 → 立即查询（适合单户抽查，不适合批量自动化）

## 已验证接口清单

| 用途 | 接口 | 加密 | 说明 |
|---|---|---|---|
| 已绑定户号列表 | `POST /eleCustNumber/queryBindEleUsers` | 否（明文） | **获取绑定户号的核心接口**，body 传 `{}`，返回含 bindingId/eleCustNumber/areaCode/eleAddress/userName 等 |
| 每日电量+温度 | `POST /charge/queryDayElectricAndTemperature` | 否（明文） | 南网某省电网用户用这个，body 传 `{areaCode, eleCustId, yearMonth, meteringPointId}` |
| 每日电量明细（按计量点） | `POST /charge/queryDayElectricByMPoint` | 是（need-crypto） | 页面日历加载时调用，请求体和响应均加密 |
| 批量每日电量 | `POST /charge/queryDayElectricList` | 是（need-crypto） | 批量查询多户，请求体 param 密文，响应 data 密文 |
| 计量点信息 | `POST /charge/queryMeteringPoint` | 是（need-crypto） | 获取 meteringPointId，body 传 `{bindingId, areaCode}`，需加密头 |
| 用电日历（特定城市） | `POST /charge/queryElectricityCalendar` | 否 | 部分城市用专属端点，注意分省/分市接口分叉 |
| 电费账单 | `POST /charge/selectElecBill`、`selectElecBillDetails` | 否 | 月账单与明细，另有分省版本 |

### 核心查询链路（已跑通）

```
1. 登录 → sessionStorage.token + sessionStorage.custnumber
2. POST /eleCustNumber/queryBindEleUsers {} → 绑定户号列表（含 bindingId）
3. 对每户：POST /charge/queryDayElectricAndTemperature
   {areaCode:"<所在地区代码>", eleCustId:"<bindingId>", yearMonth:"YYYYMM", meteringPointId:""}
   → 返回 [{date:"-09-24", power:"29.15", minTemperature, maxTemperature, averageTemperature}, ...]
```

### 关键参数说明

- **eleCustId** = 绑定户号列表中的 `bindingId`（如 `J6CFGiYb`），不是用户编号
- **meteringPointId**（即 pointId）= 计量点内部 ID；**实测传空字符串 `""` 即可正常返回数据**，无需浏览器 UI 收集；该 ID 仍可通过 Vuex `currentUserNumInfo.pointId` 获取但非必需
- **areaCode** = 所在地区代码（不同区域不同值，脚本默认带一个已验证值，跨区需按实际修改）
- **yearMonth** = `YYYYMM` 格式
- **date** 响应格式 = `-09-24`（需拼接年份：`yearMonth[:4] + date` → `2026-09-24`）

### meteringPointId 获取方法（可选）

`queryMeteringPoint` 接口带 `need-crypto` 加密，Python 无法直接调用。如需收集 pointId，可用 Playwright 在页面内切换户号后读取 Vuex store `currentUserNumInfo.pointId`。

## Token 管理与续期

- token 存储在浏览器 `sessionStorage.token`，`custNumber` 在 `sessionStorage.custnumber`
- Python 脚本从 config.json 读取 token/custNumber，直接用 urllib 调用明文接口
- token 失效时接口返回 `sta=04`，脚本检测后弹出 Windows 桌面提醒（PowerShell MessageBox）
- **token 有效期约数天**（服务端会话令牌，无法通过配置延长）；token 存于 `sessionStorage`，浏览器会话/重启也会丢失
- **无免短信验证码登录**：登录页虽提供"密码登录"页签，但表单仍强制"验证码 + 获取验证码"，验证码必填
- 续期方法（省事）：
  1. 浏览器打开 95598.csg.cn 登录
  2. F12 Console 执行 `copy(sessionStorage.getItem('token') + '|' + sessionStorage.getItem('custnumber'))`
  3. 运行 `python scripts/nw_token_update.py --config <config.json>`，粘贴剪贴板内容
  - 或 Playwright 全自动登录（填手机号 → 发验证码 → 用户报一次验证码 → 勾选协议 → 登录）→ 提取新 token → 调 `queryBindEleUsers` 刷新各户 bindingId（token 刷新后 bindingId 会变）→ 写回 config.json

## 脚本与配置

- 脚本：`scripts/nw_daily_fetch.py`（主抓取）、`scripts/nw_token_update.py`（Token 续期）、`scripts/nw_auto_configure.py`（面向他人一键配置）
- `config.json`：token、custNumber、areaCode、飞书 webhook、告警阈值、`meter_users` 映射表（户号↔bindingId↔pointId）

### 脚本核心逻辑

1. **token 检测**：调 `queryBindEleUsers`，sta=04 则弹窗提醒 + 退出
2. **抓取**：对 config 中 `meter_users` 逐户调 `queryDayElectricAndTemperature`
3. **落盘**：openpyxl 写 Excel（无 openpyxl 则降级 CSV），表头：用户编号/用电地址/日期/用电量(千瓦时)/估算电费(元)/最低温/最高温/均温
4. **飞书提醒**：只看最新日期数据，日电量 > 阈值 或 日估算电费 > 阈值 → 推送飞书卡片
5. **防重复**：`.last_alert_YYYY-MM-DD.json` 标记文件，同日已推送则跳过
6. **月初容错**：本月数据未发布（T+3）时自动回退抓上月
7. **电价估算**：默认 0.696 元/度，可用 `--price` 参数或 config 覆盖

## 户号绑定

绑定页：`#/gd/my/my/houseNumBinding`。两种通道：

- **「手机号查询」批量绑定**：查登录手机号名下户号，勾选未绑户号后批量绑定（单次约 10 户）
- **「用户编号 + 代扣银行卡后 6 位」逐户绑定**：适用于户号不在登录手机号名下（如单位/公共设施电表）。选「用户编号验证」→ 填 16 位用户编号 + 该户代扣银行卡后 6 位 → 立即查询 → 核对 → 勾选 → 立即绑定（每户约 30 秒）

关键细节：
- 绑定完成后调 `queryBindEleUsers` 拿全新增户的 bindingId 写入 config
- **Vue 表单必须用 Playwright fill 填值**：JS 原生 setter 赋值后界面有值但 Vue 数据模型不更新，提交后无请求发出
- 每户绑定完成后须重新导航整页再操作下一户
- 页面偶发加载遮挡致 click 超时，改用 evaluate 直接 `el.click()` 绕过

## 单账号绑定上限

- **单账号最多绑定约 26 户**（接口返回 "你已绑定 N 户，最多可选择 26 户"）
- 需监控更多户时：准备多个账号，或先解绑再绑

## 户号解绑

UI 无解绑入口，只能调 API：

```
POST https://95598.csg.cn/ucs/ma/wt/eleCustNumber/unBindElectricityUsers
Header: x-auth-token, custNumber
Body: {"bindingIds": ["id1","id2",...]}
```

- 支持批量解绑（一次传多个 bindingId）
- **必须使用最新 bindingId**：bindingId 在每次登录/token 刷新后可能变化，解绑前必须先调 `queryBindEleUsers` 获取当前有效值；使用过期 bindingId 返回 `sta:02`

## bindingId 不稳定性

- bindingId 在 token 刷新/重新登录后会变化
- **任何绑定/解绑/查询操作前，必须先调 `queryBindEleUsers` 获取最新 bindingId**，不可复用 config 中的旧值
- 手抄 bindingId 极易出错（如 `J6CFGiYb` 抄成 `J6CGiYb`），尽量用接口返回值程序化写入

## 探查方法（受限网络下提取 SPA 接口清单）

1. Playwright 打开目标站，看网络请求面板已发生的 XHR，确认请求头与响应格式
2. 本机 `Invoke-WebRequest` 直接下载 JS 包失败时，改用 **Playwright evaluate 在页面上下文内 `fetch('/js/app.xxx.js')`**（同源请求不受限），再：
   - 正则 `url:"/xxx"` 提取全量接口路径
   - 按关键词（calendar/daily/electricRecord/login）取上下文，定位参数与前端函数名
3. JS 文件名带构建版本号，从网络面板静态请求列表获取
4. 加密接口识别：JS 中带 `headers:{"need-crypto":!0}` 的接口请求体和响应体均加密（AES-128-CBC + ZeroPadding）

## 登录流程陷阱（实测）

- **协议复选框必须先勾选再点登录**：若未勾选直接点"登录"会弹"需要您进行授权"弹窗，弹窗关闭后验证码可能已过期。正确流程：填手机号 → 获取验证码 → 填验证码 → 勾选协议 → 点登录
- **验证码有效期短**：从获取到提交窗口约 60 秒（按钮倒计时），协议弹窗打断后极易过期（返回 `sta:0001003`）
- **地区默认非目标地区**：登录后首页可能显示其他默认城市，须手动"切换地区"到所在城市

## sendMsg 接口行为

- `POST /center/sendMsg` 请求体仅含 `{areaCode, phoneNumber, smsMsgType, vcType, infoType}`，**不校验手机号是否为该户号的预留手机号**——只要手机号格式正确就会发送短信
- 真正的预留手机号校验发生在 `POST /charge/queryChargesWithCode`（首页"电费查询"入口）：若手机号与户号预留手机号不匹配，返回 `sta:02`"请输入供电局预留的手机号"
- **结论**：`sendMsg` 成功 ≠ 预留手机号匹配；不能以"收到验证码"判断该手机号可绑定/查询该户号

## 历史数据可用范围

- `queryDayElectricAndTemperature` 可查到约 **前 17 个月**的日级数据（更早返回 `sta:09, "无此用户数据"`）
- 更早的历史通常仅有月度账单清单数据（长周期趋势分析用）

## 未绑定户号的异动分析方法

当日级数据因户号未绑定无法获取时，可用月度电费清单做异动分析：

1. 从月度台账中按用户编号提取目标户
2. 计算每户月度电量/电费序列，取前 6 个月中位数为"基线月均"
3. 环比增长率 = (当月 - 上月) / 上月 × 100%
4. 基线增长率 = (当月 - 基线月均) / 基线月均 × 100%
5. 突变判定：基线增长率 ≥ 50% 为严重异动

## 关键坑位

- **地区默认可能错误**：H5 顶栏默认可能为某大城市，须"切换地区"到所在城市，否则路由到非对应接口
- **广东/城市接口分叉**：同一功能可能有两套端点（用电日历最典型），不同区域用不同端点
- **T+3 发布**：用电数据 T+3 发布（如 1 月 1 日用电量最迟 1 月 4 日可查）；定时任务与告警阈值按 T+3 设计
- **用户编号前导零**：清单中为 16 位文本，CSV/浮点导出会丢前导零变 15 位；调接口前必须归一化补零到 16 位
- **eleCustId ≠ 用户编号**：eleCustId 是 bindingId，不是 16 位用户编号
- **DNS 偶发抖动**：内网 DNS 偶发解析失败（getaddrinfo failed），重试即可恢复
- **Vue 表单填充**：南网在线为 Vue SPA，自动化填表必须用 Playwright fill/type
- **绑定页状态残留**：绑定页从结果页返回或绑定成功后，须重新导航整页再操作下一户