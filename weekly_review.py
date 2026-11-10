#!/usr/bin/env python3
"""每周复盘：读内容生产表，只输出「本周发生了什么 + 下周改哪一件事」。

用法：
  python3 weekly_review.py            # 本周（周一 00:00 ~ 现在）
  python3 weekly_review.py --weeks 2  # 连上周一起看（样本太少时用）

规则化结论，不做漂亮报表。数据不足就直说不足，绝不编数。
"""

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BASE = "MUYVbTkkiawQkIssZxRcAAxHnGf"
TABLE = "tblF23HauKZqae65"
LARK = "lark-cli"
WORKDIR = "/tmp"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKDIR)
    if r.returncode != 0:
        sys.exit(f"命令失败: {' '.join(cmd)}\n{r.stderr[-1200:]}")
    return r.stdout


def fetch_records():
    man = json.loads(run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE]))
    p = man.get("record_file")
    if not p:
        sys.exit("manifest 缺 record_file")
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def sel(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def parse_dt(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=1)
    a = ap.parse_args()

    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    start = dt.datetime.combine(monday - dt.timedelta(days=7 * (a.weeks - 1)), dt.time())
    end = dt.datetime.combine(today, dt.time(23, 59))

    rows = fetch_records()
    posted = []
    for r in rows:
        if sel(r.get("状态")) != "已发":
            continue
        when = parse_dt(r.get("计划发布")) or parse_dt(r.get("创建时间"))
        if when and start <= when <= end:
            posted.append((when, r))

    def inter(r):
        return sum(int(r.get(k) or 0) for k in ("点赞", "收藏", "评论"))

    print(f"# 内容周报 {start:%m-%d} ~ {today:%m-%d}")
    if not posted:
        print("\n本周发布 0 篇。")
    else:
        by_type = defaultdict(list)
        for when, r in posted:
            by_type[sel(r.get("类型")) or "?"].append(inter(r))
        print(f"\n本周发布 {len(posted)} 篇，总互动 {sum(inter(r) for _, r in posted)}")
        print("\n| 发布日 | 类型 | 标题 | 赞 | 藏 | 评 |")
        print("|---|---|---|---|---|---|")
        for when, r in sorted(posted):
            print(f"| {when:%m-%d} | {sel(r.get('类型'))} | {r.get('标题')} | "
                  f"{r.get('点赞') or 0} | {r.get('收藏') or 0} | {r.get('评论') or 0} |")
        if len(posted) >= 3:
            print("\n按类型平均互动：")
            for t, v in sorted(by_type.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
                print(f"- {t}: {sum(v)/len(v):.1f}（{len(v)} 篇）")
        zero = [r for _, r in posted if inter(r) == 0]
        if zero:
            print(f"\n0 互动 {len(zero)} 篇：" + "、".join(str(r.get("标题"))[:18] for r in zero))
            print("→ 只改一个变量：曝光低换封面，有点击没互动换标题。别同时改。")

    # 池子与卡点
    allstates = defaultdict(int)
    for r in rows:
        allstates[sel(r.get("状态")) or "?"] += 1
    ready = [r for r in rows if sel(r.get("状态")) in ("选题", "待写")]
    stocked = [r for r in ready if r.get("素材到位")]
    print(f"\n## 池子：可开工 {len(stocked)} / 候选 {len(ready)} 条 | 已发累计 {allstates.get('已发',0)} 条")
    if not stocked:
        print("→ 下周唯一动作：给 1 条选题补齐素材（截图 + 场景/做法/效果三句话）。没素材就别开工，写了也是空话。")

    # 门槛（首月 20 篇 / 500 粉；第二月首个产品首单）
    total_posted = allstates.get("已发", 0)
    print(f"\n## 门槛：累计已发 {total_posted}/20 篇（首月目标）")
    if total_posted > 0 and total_posted < 20:
        left = 20 - total_posted
        print(f"→ 还差 {left} 篇。按每周 4 篇算，需要 {(left + 3)//4} 周。")


if __name__ == "__main__":
    main()
