# -*- coding: utf-8 -*-
"""
南网电表哨兵 - 面向他人一键配置向导（辅助脚本）

作用：让同事/他人用各自的手机号登录南网在线、绑定自己的电表户号、配置飞书提醒，
      一键生成一份「独立可用的 config.json」，与技能作者的原配置互不干扰。

本脚本只负责「信息收集 + 校验 + 生成独立配置骨架 + 输出操作清单」，
浏览器登录、短信验证码、绑户、提 token 等需实时人工配合的动作，由 AI 按
脚本输出的「Playwright 操作清单」引导用户完成（需验证码，无法纯脚本自动化）。

用法：
    python nw_auto_configure.py --user 张三 --phone 13900000000 \
        --users 0308200000000001,0308200000000002 \
        --config-dir D:/文档/电费分析/南网在线每日电费/user_zhangsan

参数说明：
    --user        使用者标识（用于目录命名与 accounts 注释，如 张三）
    --phone       新用户南网在线登录手机号（11 位）
    --users       待绑定 16 位用户编号清单（逗号分隔，户号不在本人名下时后续还需银行卡后6位）
    --config-dir  新用户独立配置目录（缺省则自动生成在脚本同目录 ./user_<标识>）
    --card6       代扣银行卡后 6 位（可选，户号不在手机号名下时提供，由 AI 填入绑定表单）
    --feishu      飞书机器人 webhook（可选，留空则生成后人工补填）
    --no-print    不打印操作清单（只生成骨架）

脚本只依赖标准库。生成的 config.json 为空 token（待登录后回填），
绑定户号列表为空（待 Playwright 绑户后回填）。
"""
import sys
sys.dont_write_bytecode = True  # 禁止生成 __pycache__/.pyc（技能发布审核要求）
import argparse
import json
import os
import re
import sys

# 默认电表分类阈值（与 nw_daily_fetch.py 保持一致）
DEFAULT_METER_GROUPS = {
    "fangnishui": {"name": "防溺水监控", "alert_power": 1.5, "alert_mode": "power_only"},
    "base_station": {"name": "基站", "alert_power": 25, "alert_mode": "power_only"},
    "access_room": {"name": "接入网机房", "alert_power": 85, "alert_mode": "power_only"},
    "comprehensive_room": {"name": "综合机房", "alert_power": 717, "alert_mode": "power_only"},
    "security_monitor": {"name": "治安视频监控", "alert_power": 1.5, "alert_mode": "power_only"},
}

AREA_CODE = "030800"


def normalize_house_no(s):
    """归一化用户编号：去掉空格，缺失前导零则补到 16 位（0308 开头）"""
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace(" ", "")
    if s.isdigit() and len(s) == 15 and s.startswith("308"):
        s = "0" + s
    return s


def validate_phone(p):
    p = (p or "").strip()
    if not re.fullmatch(r"1[3-9]\d{9}", p):
        return False
    return True


def build_config(phone, feishu="", meter_classification_file="meter_classification.json"):
    return {
        "token": "",                       # 登录后回填
        "custNumber": "",                  # 登录后回填
        "areaCode": AREA_CODE,
        "token_updated": "",
        "feishu_webhook_url": feishu,
        "alert_threshold": {
            "daily_fee": 1.5,
            "daily_power": 1.5,
            "mode": "power_only"
        },
        "meter_groups": DEFAULT_METER_GROUPS,
        "meter_classification_file": meter_classification_file,
        "accounts": {
            phone: "新配置"
        },
        "meter_users": []                 # 登录绑户后回填
    }


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print("[OK] 已生成配置骨架:", path)


def print_guide(phone, user, users, config_dir, card6):
    print("\n" + "=" * 70)
    print("面向他人一键配置向导 - 执行清单（AI 按此操作）")
    print("=" * 70)
    print("目标用户:", user or phone)
    print("登录手机号:", phone)
    print("新配置目录:", config_dir)
    print("待绑户号:", ", ".join(users) if users else "（暂未提供）")
    print("银行卡后6位:", card6 or "（未提供）")
    print("-" * 70)
    print("步骤 1/5  登录南网在线（需用户报一次短信验证码）")
    print("   Playwright 打开 https://95598.csg.cn/#/sz/login/login")
    print("   填手机号", phone, "→ 点发送验证码 → 等用户报验证码")
    print("   填验证码 → 【先勾选用户协议复选框】→ 点登录（切换地区到所在城市）")
    print()
    print("步骤 2/5  提取 token + custNumber，写入新 config")
    print("   从 sessionStorage 读 token / custnumber，写入:")
    print("   ", config_dir + "\\config.json  (token / custNumber)")
    print()
    print("步骤 3/5 绑定电表户号")
    if users:
        print("   导航到 #/gd/my/my/houseNumBinding（每户绑完须重新导航整页）")
        print("   若户号在手机号名下 → 选「手机号查询」批量勾选绑定")
        print("   若户号不在名下（如防溺水/基站）→ 选「用户编号验证」")
        print("       填 16 位用户编号 + 代扣银行卡后6位（", card6 or "待用户提供", "）")
        print("       立即查询 → 勾选 → 立即绑定")
    else:
        print("   用户未提供户号，暂不绑户（后续可对话追加）")
    print()
    print("步骤 4/5  同步户号信息到 config")
    print("   调 POST /eleCustNumber/queryBindEleUsers → 拿最新 bindingId")
    print("   自动识别电表类型 → 填入 config.json 的 meter_users")
    print()
    print("步骤 5/5  配置飞书 + 部署定时任务")
    print("   若用户提供了 webhook，写入 feishu_webhook_url")
    print("   创建 Windows 计划任务（每天 09:00）: python nw_daily_fetch.py --config <config路径>")
    print("   试运行一次抓取验证链路")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="南网电表哨兵-面向他人一键配置向导")
    ap.add_argument("--user", default="", help="当前用户标识，如 张三")
    ap.add_argument("--phone", required=True, help="南网在线登录手机号")
    ap.add_argument("--users", default="", help="16位户号清单，逗号分隔")
    ap.add_argument("--config-dir", default="", help="新用户独立配置目录")
    ap.add_argument("--feishu", default="", help="飞书 webhook")
    ap.add_argument("--card6", default="", help="代扣银行卡后6位（可选）")
    ap.add_argument("--force", action="store_true", help="目录存在时覆盖")
    ap.add_argument("--no-print", action="store_true", help="不打印操作清单")
    args = ap.parse_args()

    phone = args.phone.strip()
    if not validate_phone(phone):
        print("[错误] 手机号格式不正确:", phone)
        sys.exit(1)

    users = [normalize_house_no(u) for u in args.users.split(",") if u.strip()]
    bad = [u for u in users if len(u) != 16]
    if bad:
        print("[错误] 存在非 16 位户号:", bad)
        sys.exit(1)

    # 确定配置目录
    if args.config_dir:
        config_dir = args.config_dir
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        tag = re.sub(r"[^\w\u4e00-\u9fff]", "_", args.user or phone)
        config_dir = os.path.join(base, "user_" + tag)
    os.makedirs(config_dir, exist_ok=True)

    config_path = os.path.join(config_dir, "config.json")
    if os.path.exists(config_path) and not args.force:
        print("[警告] 目标配置已存在，跳过写入（如需覆盖请加 --force）:", config_path)
    else:
        cfg = build_config(phone, args.feishu.strip())
        write_json(config_path, cfg)

    if not args.no_print:
        print_guide(phone, args.user.strip(), users, config_dir, args.card6.strip())


if __name__ == "__main__":
    main()