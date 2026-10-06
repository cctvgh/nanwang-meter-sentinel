# -*- coding: utf-8 -*-
"""
南网在线每日电费抓取脚本
================================
      功能：根据 config.json 中的监控电表用户编号 + bindingId 映射，
      调用南网在线 95598.csg.cn 明文接口，抓取每日电量数据，落盘 Excel；
      当日电量 > 阈值 或 日估算电费 > 阈值 时，推送飞书提醒。
    2026-09-26 更新：改为读取 meter_users，
      meteringPointId 传空字符串即可，无需浏览器UI收集。

用法：
    python nw_daily_fetch.py                 # 抓取本月（截至昨天）每日电量
    python nw_daily_fetch.py 202609          # 抓取指定月份
    python nw_daily_fetch.py --price 0.696   # 指定电价估算电费
    python nw_daily_fetch.py --no-alert      # 跳过飞书提醒
    python nw_daily_fetch.py --alert-fee 2.0 --alert-power 3.0  # 覆盖告警阈值
    python nw_daily_fetch.py --config D:/path/config.json   # 指定配置文件（默认脚本同目录 config.json）

数据说明：
    - 接口返回的是【每日用电量】（千瓦时/度），T+3 天发布（例：1月1日数据最晚1月4日可查）
    - 日电费不直接提供，脚本按电价估算；如电价与实际不符，请用 --price 覆盖
    - 数据仅供参考，抄表算费以实际电费单为准

依赖：Python 3.8+（标准库 urllib；openpyxl 可选，无则自动落 CSV）
"""
import sys
sys.dont_write_bytecode = True  # 禁止生成 __pycache__/.pyc（技能发布审核要求）
import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
API_BASE = "https://95598.csg.cn/ucs/ma/wt"
DEFAULT_PRICE = 0.696  # 元/千瓦时（参考均价，可 --price 覆盖）

# 默认提醒阈值：日估算电费 > 1.5 元 或 日用电量 > 1.5 度
DEFAULT_ALERT_FEE = 1.5
DEFAULT_ALERT_POWER = 1.5


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("配置文件不存在: %s" % CONFIG_PATH)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print("配置文件 JSON 格式错误: %s\n%s" % (CONFIG_PATH, e))
        sys.exit(1)


def api_raw(cfg, path, body):
    """调用南网在线接口（明文，x-auth-token 认证），返回解析后的 JSON"""
    url = API_BASE + path
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-auth-token", cfg["token"])
    req.add_header("custNumber", cfg.get("custNumber", ""))
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
    req.add_header("Referer", "https://95598.csg.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_day_electric(cfg, ele_cust_id, point_id, year_month):
    """
    查询单户某月每日电量
    ele_cust_id: bindingId（config 中 meter_users.bindingId）
    point_id:    meteringPointId（config 中 meter_users.pointId）
    返回: [{date:"-09-24", power:"29.15", ...}, ...]
    """
    body = {
        "areaCode": cfg.get("areaCode", "030800"),
        "eleCustId": ele_cust_id,
        "yearMonth": year_month,
        "meteringPointId": point_id,
    }
    try:
        r = api_raw(cfg, "/charge/queryDayElectricAndTemperature", body)
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:200]))
    if r.get("sta") != "00":
        raise RuntimeError("接口错误: %s" % json.dumps(r, ensure_ascii=False)[:200])
    return r.get("data") or []


def load_classification(cfg):
    """加载电表分类映射表，返回 {用户编号(15位): 类型键}"""
    cls_file = cfg.get("meter_classification_file", "")
    if not cls_file:
        return {}
    cls_path = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), cls_file)
    if not os.path.exists(cls_path):
        return {}
    with open(cls_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 键统一为15位（去掉前导0）
    return {k.lstrip("0").zfill(15): v.get("type", "unknown") for k, v in data.items()}


def get_user_group(u, cls_map):
    """确定用户所属电表分类，优先用户条目中的 group 字段"""
    if u.get("group"):
        return u["group"]
    num15 = str(u.get("eleCustNumber", "")).lstrip("0").zfill(15)
    return cls_map.get(num15, "unknown")


def get_group_threshold(cfg, group_key):
    """获取某分类的告警阈值 (fee_th, power_th, mode)，缺省回退全局"""
    groups = cfg.get("meter_groups", {})
    g = groups.get(group_key, {})
    global_th = cfg.get("alert_threshold", {})
    fee_th = g.get("alert_fee", global_th.get("daily_fee", DEFAULT_ALERT_FEE))
    power_th = g.get("alert_power", global_th.get("daily_power", DEFAULT_ALERT_POWER))
    mode = g.get("alert_mode", global_th.get("mode", "both"))
    return fee_th, power_th, mode


GROUP_NAMES = {
    "fangnishui": "防溺水监控",
    "base_station": "基站",
    "access_room": "接入网机房",
    "comprehensive_room": "综合机房",
    "security_monitor": "治安视频监控",
    "unknown": "未分类",
}


def fetch_month(cfg, year_month, price, cls_map=None):
    """抓取所有绑定户号某月每日电量，返回明细行（含电表分类）"""
    rows = []
    # 优先读取 meter_users（兼容旧键 fangnishui_users）
    users = cfg.get("meter_users", []) or cfg.get("fangnishui_users", [])
    if cls_map is None:
        cls_map = load_classification(cfg)
    for u in users:
        bid = u.get("bindingId", "")
        pid = u.get("pointId", "")  # 可传空字符串
        group = get_user_group(u, cls_map)
        group_name = GROUP_NAMES.get(group, group)
        try:
            data = query_day_electric(cfg, bid, pid, year_month)
            for d in data:
                date_str = year_month[:4] + d.get("date", "")
                power = float(d.get("power") or 0)
                rows.append({
                    "用户编号": u["eleCustNumber"],
                    "电表类型": group_name,
                    "group": group,
                    "用电地址": u.get("eleAddress", ""),
                    "日期": date_str,
                    "用电量(千瓦时)": power,
                    "估算电费(元)": round(power * (price if price is not None else DEFAULT_PRICE), 2),
                    "最低温": d.get("minTemperature", ""),
                    "最高温": d.get("maxTemperature", ""),
                    "均温": d.get("averageTemperature", ""),
                })
            print("  [%s] %s  %s  OK %d 天" % (group_name, u["eleCustNumber"], u.get("eleAddress", ""), len(data)))
        except Exception as e:
            rows.append({
                "用户编号": u["eleCustNumber"],
                "电表类型": group_name,
                "group": group,
                "用电地址": u.get("eleAddress", ""),
                "日期": year_month,
                "用电量(千瓦时)": "",
                "估算电费(元)": "",
                "错误": str(e)[:120],
            })
            print("  [%s] %s %s  失败: %s" % (group_name, u["eleCustNumber"], u.get("eleAddress", ""), e))
    return rows


ROW_HEADERS = ["用户编号", "电表类型", "group", "用电地址", "日期",
               "用电量(千瓦时)", "估算电费(元)", "最低温", "最高温", "均温", "错误"]


def to_excel(rows, out_path):
    """生成 Excel（openpyxl 可选）；无 openpyxl 时落 CSV"""
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "每日电量"
        if rows:
            ws.append(ROW_HEADERS)
            for r in rows:
                ws.append([r.get(h, "") for h in ROW_HEADERS])
        wb.save(out_path)
        return "xlsx"
    except ImportError:
        import csv
        csv_path = out_path.replace(".xlsx", ".csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=ROW_HEADERS)
            writer.writeheader()
            for r in rows:
                writer.writerow({h: r.get(h, "") for h in ROW_HEADERS})
        return "csv"


def check_token(cfg):
    """
    检测 token 是否有效。返回 (状态, 提示信息)。
    状态: 'ok' 有效 / 'expired' token失效 / 'error' 网络/接口异常
    """
    try:
        r = api_raw(cfg, "/eleCustNumber/queryBindEleUsers", {})
        if r.get("sta") == "00":
            return 'ok', ""
        if r.get("sta") == "04":
            return 'expired', "Token 已过期，请重新登录"
        return 'error', "接口返回异常: %s" % json.dumps(r, ensure_ascii=False)[:200]
    except urllib.error.URLError as e:
        return 'error', "网络异常: %s" % e
    except Exception as e:
        return 'error', str(e)[:200]


def show_reminder(title, message):
    """Windows 桌面弹窗提醒（PowerShell MessageBox）"""
    try:
        # 转义单引号防止 PowerShell 注入
        msg = message.replace("'", "''")
        ttl = title.replace("'", "''")
        ps = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;"
            "[System.Windows.Forms.MessageBox]::Show('%s','%s','OK','Warning')" % (msg, ttl)
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass


def send_feishu_alert(cfg, alerts):
    """
    通过飞书 Webhook 推送提醒消息（按电表类型分组展示）。
    alerts: 需要提醒的记录列表（每条含 用户编号/电表类型/用电地址/日期/用电量/估算电费/触发原因/告警阈值）
    """
    url = cfg.get("feishu_webhook_url", "")
    if not url:
        print("config.json 未配置 feishu_webhook_url，跳过飞书推送")
        return

    total = len(alerts)
    today = datetime.date.today().strftime("%Y-%m-%d")

    # 按电表类型分组
    from collections import defaultdict
    by_type = defaultdict(list)
    for a in alerts:
        by_type[a.get("电表类型", "未分类")].append(a)

    # 构造摘要
    summary_parts = []
    for type_name, type_alerts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        summary_parts.append("%s %d户" % (type_name, len(type_alerts)))
    summary = "、".join(summary_parts)

    # 构造明细（按类型分段，每段最多20条）
    lines = []
    shown = 0
    for type_name, type_alerts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        lines.append("**%s（阈值 %s，%d 户超标）**" % (type_name, type_alerts[0].get("告警阈值", "-"), len(type_alerts)))
        for a in type_alerts[:20]:
            lines.append(
                "  %s %s\n"
                "    日期 %s｜电量 %s 度｜电费 %s 元｜%s" % (
                    a.get("用户编号", ""),
                    a.get("用电地址", ""),
                    a.get("日期", ""),
                    a.get("用电量(千瓦时)", ""),
                    a.get("估算电费(元)", ""),
                    a.get("触发原因", ""),
                )
            )
            shown += 1
            if shown >= 50:
                break
        if shown >= 50:
            lines.append("… 等共 %d 条" % total)
            break

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "⚡ 南网电表异动提醒"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**日期：** %s\n"
                            "**触发汇总：** %s\n"
                            "**总计：** %d 户超标"
                        ) % (today, summary, total),
                    },
                },
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "数据来源：南网在线（T+3 发布，仅供参考）"}]},
            ],
        },
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("code") == 0:
                print("飞书提醒已发送，共 %d 条" % total)
            else:
                print("飞书推送失败: %s" % body[:200])
    except Exception as e:
        print("飞书推送异常: %s" % e)


def _filter_alerts(latest, fee_threshold, power_threshold, mode):
    """公共筛选逻辑：按阈值+模式筛选告警行"""
    alerts = []
    for r in latest:
        power = r.get("用电量(千瓦时)", 0) or 0
        fee = r.get("估算电费(元)", 0) or 0
        reasons = []
        if mode in ("both", "power_only") and power > power_threshold:
            reasons.append("电量超标(%.1f度)" % power_threshold)
        if mode in ("both", "fee_only") and fee > fee_threshold:
            reasons.append("电费超标(%.1f元)" % fee_threshold)
        if reasons:
            r["触发原因"] = "+".join(reasons)
            r["告警阈值"] = "%.1f度" % power_threshold
            alerts.append(r)
    return alerts


def build_alerts(rows, fee_threshold, power_threshold, mode="both"):
    """
    全局单阈值告警筛选（只看最新日期）。
    返回: (告警列表, 最新日期, 标记文件路径)；若当日已发送则返回空列表。
    """
    if not rows:
        return [], None, None
    valid = [r for r in rows if r.get("用电量(千瓦时)") not in (None, "")]
    if not valid:
        return [], None, None
    latest_date = max(r["日期"] for r in valid)
    latest = [r for r in valid if r["日期"] == latest_date]
    sent_file = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)),
                             ".last_alert_%s.json" % latest_date)
    if os.path.exists(sent_file):
        print("日期 %s 的提醒已发送过，跳过" % latest_date)
        return [], latest_date, sent_file
    alerts = _filter_alerts(latest, fee_threshold, power_threshold, mode)
    return alerts, latest_date, sent_file


def build_alerts_multi(rows, cfg):
    """
    按电表分类差异化阈值筛选告警（只看最新日期）。
    返回: (告警列表, 最新日期, 标记文件路径)；若当日已发送则返回空列表。
    """
    if not rows:
        return [], None, None
    valid = [r for r in rows if r.get("用电量(千瓦时)") not in (None, "")]
    if not valid:
        return [], None, None
    latest_date = max(r["日期"] for r in valid)
    latest = [r for r in valid if r["日期"] == latest_date]
    sent_file = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)),
                             ".last_alert_%s.json" % latest_date)
    if os.path.exists(sent_file):
        print("日期 %s 的提醒已发送过，跳过" % latest_date)
        return [], latest_date, sent_file
    alerts = []
    for r in latest:
        group = r.get("group", "unknown")
        fee_th, power_th, mode = get_group_threshold(cfg, group)
        r_alerts = _filter_alerts([r], fee_th, power_th, mode)
        alerts.extend(r_alerts)
    return alerts, latest_date, sent_file


def current_month():
    return datetime.datetime.now().strftime("%Y%m")


def main():
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="南网在线每日电费抓取")
    parser.add_argument("month", nargs="?", help="月份 YYYYMM，缺省为本月")
    parser.add_argument("--price", type=float, default=DEFAULT_PRICE, help="估算电价(元/度)")
    parser.add_argument("--no-alert", action="store_true", help="跳过飞书提醒")
    parser.add_argument("--config", default=CONFIG_PATH, help="config.json 路径（默认脚本同目录）")
    parser.add_argument("--alert-fee", type=float, default=None, help="日估算电费告警阈值(元)，覆盖 config.json")
    parser.add_argument("--alert-power", type=float, default=None, help="日用电量告警阈值(度)，覆盖 config.json")
    parser.add_argument("--alert-mode", choices=["both", "power_only", "fee_only"], default=None,
                        help="告警模式：both 电量或电费任一超标；power_only 仅电量；fee_only 仅电费")
    args = parser.parse_args()
    CONFIG_PATH = os.path.abspath(args.config)

    cfg = load_config()
    if not cfg.get("token"):
        show_reminder("南网在线抓取失败", "config.json 缺少 token，请登录南网在线后更新")
        print("config.json 缺少 token，请登录南网在线后更新")
        sys.exit(1)

    # Token 有效性检测：区分 token 失效与网络异常
    token_status, err = check_token(cfg)
    if token_status == 'expired':
        msg = ("南网在线登录已失效（Token 过期）！\n"
               "请打开 https://95598.csg.cn 重新登录，\n"
               "然后把浏览器里的 token 更新到 config.json。\n\n错误: %s" % err)
        show_reminder("南网在线 Token 失效", msg)
        print("Token 失效: %s" % err)
        sys.exit(2)
    elif token_status == 'error':
        print("警告: Token 校验失败（%s），继续尝试抓取..." % err)

    month = args.month or current_month()
    users = cfg.get("meter_users", []) or cfg.get("fangnishui_users", [])
    cls_map = load_classification(cfg)
    print("抓取月份: %s  绑定户数: %d  分类表: %d 户" % (month, len(users), len(cls_map)))
    if not users:
        print("config.json 的 meter_users 为空，请先补充映射")
        sys.exit(1)

    rows = fetch_month(cfg, month, args.price, cls_map)

    # 月初容错：仅在未指定月份时自动回退抓上月（T+3 延迟）
    if args.month is None and (not rows or all(r.get("用电量(千瓦时)") in (None, "") for r in rows)):
        prev = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).strftime("%Y%m")
        print("本月 %s 暂无数据，回退抓取上月 %s" % (month, prev))
        month = prev
        rows = fetch_month(cfg, month, args.price, cls_map)

    if not rows:
        print("无数据返回")
        return

    out_path = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)),
                            "南网每日电量_%s.xlsx" % month)

    # 2026-10-02 增加数据保护：全部户号抓取失败时，绝不覆盖已存在的月度 Excel。
    # 事故案例：2026-10-02 09:00 定时任务遇 DNS 抖动，错误行覆盖了 202609/202610 两个月好数据，
    # 仅靠事后按月全量重抓才恢复。此校验确保网络故障时保留磁盘上的历史数据。
    valid_rows = [r for r in rows if r.get("用电量(千瓦时)") not in (None, "")]
    if not valid_rows:
        if os.path.exists(out_path):
            print("FATAL: %s 月全部户号抓取失败，为保护已有数据，跳过覆盖 %s" % (month, out_path))
            print("本次不写入任何文件。请检查网络（DNS 常见 getaddrinfo failed，重试即恢复）后重跑。")
            sys.exit(3)
        print("警告: %s 月全部户号抓取失败，%s 不存在，仅落盘错误记录用于排查" % (month, out_path))

    fmt = to_excel(rows, out_path)
    print("已保存: %s (%s)" % (out_path, fmt))
    print("共 %d 条记录" % len(rows))

    # 飞书提醒：按电表分类差异化阈值告警
    if not args.no_alert:
        send_ok = False
        if args.alert_fee is not None or args.alert_power is not None or args.alert_mode is not None:
            # 全局覆盖阈值模式
            fee_th = args.alert_fee if args.alert_fee is not None else cfg.get("alert_threshold", {}).get("daily_fee", DEFAULT_ALERT_FEE)
            power_th = args.alert_power if args.alert_power is not None else cfg.get("alert_threshold", {}).get("daily_power", DEFAULT_ALERT_POWER)
            mode = args.alert_mode if args.alert_mode is not None else cfg.get("alert_threshold", {}).get("mode", "both")
            mode_label = {"both": "电量或电费任一超标", "power_only": "仅电量超标", "fee_only": "仅电费超标"}[mode]
            print("告警模式(全局覆盖): %s | 日电费 > %.1f 元 / 日电量 > %.1f 度" % (mode_label, fee_th, power_th))
            alerts, latest_date, sent_file = build_alerts(rows, fee_th, power_th, mode)
        else:
            # 多分类差异化告警
            groups = cfg.get("meter_groups", {})
            print("按电表分类差异化告警:")
            for gk, gv in groups.items():
                print("  %s: 日电量 > %.1f 度 (%s)" % (gv.get("name", gk), gv.get("alert_power", DEFAULT_ALERT_POWER), gv.get("alert_mode", "both")))
            alerts, latest_date, sent_file = build_alerts_multi(rows, cfg)
        if alerts:
            send_feishu_alert(cfg, alerts)
            # 告警标记在发送成功后写入（防止推送失败时漏报）
            try:
                with open(sent_file, "w", encoding="utf-8") as f:
                    json.dump({"date": latest_date, "count": len(alerts), "sent": True}, f, ensure_ascii=False)
            except Exception as e:
                print("警告: 告警标记文件写入失败: %s" % e)
        else:
            print("最新日期无超标户号，不推送飞书")


if __name__ == "__main__":
    main()