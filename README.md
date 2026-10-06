# 南网电表哨兵（公开版）

南网在线（95598.csg.cn）日电量自动监控与异动提醒。调用南网在线已验证接口按绑定户号抓取每日用电量（T+3 发布），按参考电价估算日电费落盘 Excel；日电量或估算电费超阈值时推送飞书提醒。支持户号绑定/解绑、Token 检测续期、电表多分类差异化告警、异常原因分析报告。

适用于物业公司、园区后勤、多户号企业、防溺水监控电表/基站/机房的日级电费异动监控。

## 特性

- 每日自动抓取全账户用电量（T+3 发布）
- 电量/电费超阈值飞书即时告警（按电表类型差异化阈值）
- 多分类电表独立管理（防溺水、基站、机房、监控等）
- 一键异常原因分析报告（HTML）
- 户号绑定/解绑、Token 自动续期工具
- 纯 Python 标准库，无第三方依赖（openpyxl 可选，缺省降级 CSV）

## 目录结构

```
nanwang-meter-sentinel/
├── SKILL.md
├── references/
│   ├── nanwang-api.md            # 南网在线 H5 接口笔记
│   ├── quick-start.md            # 新用户快速上手指南
│   ├── pitfalls.md               # 实操坑位与排查清单
│   └── anomaly-analysis-guide.md # 电表异常原因分析指南
└── scripts/
    ├── nw_daily_fetch.py         # 主抓取脚本（token 检测→逐户抓日电量→Excel→飞书提醒）
    ├── nw_token_update.py        # Token 续期写入工具
    └── nw_auto_configure.py      # 面向他人一键配置向导
```

## 快速开始

1. 登录南网在线（95598.csg.cn），浏览器 F12 提取 `token|custnumber`
2. 配置 `config.json`（token、户号清单、飞书 webhook、告警阈值）
3. 运行抓取：`python scripts/nw_daily_fetch.py`

详见 `references/quick-start.md`。

## 环境要求

- Python 3.8+（标准库 urllib）
- openpyxl（可选，缺失自动降级 CSV）

## 说明

本公开版已做对外脱敏，不含任何单位内部信息；具体户号与阈值请在 `config.json` 中按实际绑定配置。数据全程本机处理，仅与用户自建的飞书机器人通信。

## License

Apache-2.0