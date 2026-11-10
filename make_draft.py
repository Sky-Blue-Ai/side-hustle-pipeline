#!/usr/bin/env python3
"""选题 → 草稿 → 回写飞书：内容流水线的胶水层。

    flow = next(挑题) → 我写 draft.json → save(写回表 + 出封面) → 你手动发 → posted(回填)

用法：
  python3 make_draft.py next [--limit 3]         # 挑出可以开工的选题（素材到位 + 评分高）
  python3 make_draft.py save --file draft.json   # 把草稿写回表（状态→待做图）并渲染封面
  python3 make_draft.py posted --record recXXX --date 2026-11-12 [+点赞/收藏/评论]
  python3 make_draft.py stats                    # 池子水位与卡点体检

设计原则（别改）：
- 素材到位 = false 的选题一律不进批次，只报告缺什么。这是防凑数的闸门。
- 状态只前进不倒退；已发的记录不再被 next 挑中。
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "MUYVbTkkiawQkIssZxRcAAxHnGf"
TABLE = "tblF23HauKZqae65"  # 内容生产
LARK = "lark-cli"
WORKDIR = "/tmp"  # lark-cli 不允许写 /root 下目录

PICKABLE = ("选题", "待写")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKDIR, **kw)
    if r.returncode != 0:
        sys.exit(f"命令失败: {' '.join(cmd)}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def fetch_records(table=TABLE):
    raw = run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", table])
    try:
        man = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(f"没解析到 manifest:\n{raw[:800]}")
    path = man.get("record_file")
    if not path:
        sys.exit("manifest 里没有 record_file")
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    if man.get("has_more"):
        print("⚠ 表还有更多页没取到，统计可能不全", file=sys.stderr)
    return rows


def sel(v):
    """select 字段取第一个值。"""
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def pick(rows, limit=3):
    ready, blocked = [], []
    for r in rows:
        st = sel(r.get("状态"))
        if st not in PICKABLE:
            continue
        item = {
            "record_id": r.get("record_id"),
            "title": r.get("标题"),
            "type": sel(r.get("类型")),
            "score": r.get("评分") or 0,
            "material_ready": bool(r.get("素材到位")),
            "素材": r.get("素材"),
            "备注": r.get("备注"),
        }
        (ready if item["material_ready"] else blocked).append(item)
    ready.sort(key=lambda x: (-x["score"], x["record_id"] or ""))
    return ready[:limit], ready[limit:], blocked


def cmd_next(a):
    rows = fetch_records()
    ready, more, blocked = pick(rows, a.limit)
    print(f"## 可以开工（素材已到位，按评分）: {len(ready)} 条")
    for it in ready:
        print(f"\n- [{it['score']}分/{it['type']}] {it['title']}")
        print(f"  record_id: {it['record_id']}")
        if it["素材"]:
            print(f"  素材: {str(it['素材'])[:400]}")
        if it["备注"]:
            print(f"  备注: {it['备注']}")
    if more:
        print(f"\n## 排队中: {len(more)} 条（同样已到位）")
        for it in more:
            print(f"- [{it['score']}分] {it['title']}")
    print(f"\n## 卡住的: {len(blocked)} 条（素材到位未勾，不会进批次）")
    for it in blocked[:10]:
        print(f"- [{it['score']}分] {it['title']} ← 缺：{it['备注'] or '一张截图 + 场景/做法/效果三句话'}")
    if blocked[10:]:
        print(f"- …还有 {len(blocked)-10} 条")
    if not ready and blocked:
        print("\n结论：池子有料但没有一条能开工。先补 1 条素材（一条也行），否则这一周是空的。")


def fmt_dt(s):
    if not s:
        return ""
    return s


def cmd_save(a):
    d = json.loads(Path(a.file).read_text(encoding="utf-8"))
    rid = d["record_id"]
    body = (d.get("body") or "").strip()
    tags = d.get("tags") or []
    titles = d.get("titles") or []
    cover = d.get("cover")

    material = body
    if tags:
        material += "\n\n标签: " + " ".join(tags)
    if cover:
        material += "\n\n封面: " + json.dumps(cover, ensure_ascii=False)

    fields = {"状态": ["待做图"], "素材": material, "素材到位": True}
    if d.get("title"):
        fields["标题"] = d["title"]
    if a.date:
        fields["计划发布"] = _dt(a.date)

    payload = {"update_records": {rid: fields}}
    run([LARK, "base", "+record-batch-update", "--base-token", BASE, "--table-id", TABLE,
         "--json", json.dumps(payload, ensure_ascii=False)])

    # 回读确认落库
    rows = fetch_records()
    row = next((r for r in rows if r.get("record_id") == rid), None)
    if not row:
        sys.exit(f"回读找不到记录 {rid}，写回可能失败")
    ok_state = sel(row.get("状态")) == "待做图"
    ok_body = (row.get("素材") or "").startswith(body[:40]) if body else False
    print(f"写回: {rid} 状态={sel(row.get('状态'))} 素材长度={len(row.get('素材') or '')} "
          f"{'✓' if ok_state and ok_body else '⚠ 校验不通过'}")

    imgs = []
    if cover and a.render:
        spec = dict(cover)
        spec.setdefault("name", _slug(d.get("title") or rid))
        tmp = Path(WORKDIR) / f"cover_spec_{rid}.json"
        tmp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out = Path(ROOT) / "out" / "covers"
        cmd = [sys.executable, str(ROOT / "render_cover.py"), "--template",
               spec.pop("template", "all"), "--data-file", str(tmp), "--outdir", str(out),
               "--name", _slug(d.get("title") or rid)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("⚠ 封面渲染失败:\n" + r.stderr[-1200:])
        else:
            imgs = [l for l in r.stdout.split() if l.endswith(".png")]
    if a.dump_titles and titles:
        print("\n10 个标题备选:")
        for i, t in enumerate(titles, 1):
            print(f"{i}. {t}")
    print("\n飞书: https://my.feishu.cn/base/%s?table=%s" % (BASE, TABLE))
    for p in imgs:
        print("COVER:", p)


def _slug(s):
    import re
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff-]+", "_", str(s))[:40] or "cover"


def _dt(s):
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    sys.exit(f"看不懂的日期: {s}")


def cmd_posted(a):
    fields = {"状态": ["已发"], "计划发布": _dt(a.date)}
    for k, v in (("点赞", a.likes), ("收藏", a.collects), ("评论", a.comments)):
        if v is not None:
            fields[k] = v
    payload = {"update_records": {a.record: fields}}
    run([LARK, "base", "+record-batch-update", "--base-token", BASE, "--table-id", TABLE,
         "--json", json.dumps(payload, ensure_ascii=False)])
    rows = fetch_records()
    row = next((r for r in rows if r.get("record_id") == a.record), None)
    if not row or sel(row.get("状态")) != "已发":
        sys.exit("回读校验失败")
    print(f"已回填 {a.record}: 状态=已发 计划发布={row.get('计划发布')} 赞={row.get('点赞')} 藏={row.get('收藏')} 评={row.get('评论')}")
    print("飞书: https://my.feishu.cn/base/%s?table=%s" % (BASE, TABLE))


def cmd_stats(a):
    rows = fetch_records()
    from collections import Counter
    states = Counter(sel(r.get("状态")) or "?" for r in rows)
    ready = sum(1 for r in rows if r.get("素材到位"))
    pool = states.get("选题", 0) + states.get("待写", 0)
    print(f"总 {len(rows)} 条 | 状态: {dict(states)}")
    print(f"素材到位: {ready} 条 | 可开工池(选题+待写): {pool} 条")
    if pool < 10:
        print("⚠ 选题池低于 10 条的警戒水位，该补料了")
    if pool > 0 and ready == 0:
        print("⚠ 池子里没有一条素材到位 —— 这是当前唯一真实的卡点，不是选题不够")
    posted = [r for r in rows if sel(r.get("状态")) == "已发"]
    print(f"已发: {len(posted)} 条")
    for r in posted:
        print(f"  - {r.get('标题')} 赞{r.get('点赞')} 藏{r.get('收藏')} 评{r.get('评论')}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("next"); p1.add_argument("--limit", type=int, default=3); p1.set_defaults(fn=cmd_next)
    p2 = sub.add_parser("save"); p2.add_argument("--file", required=True)
    p2.add_argument("--date"); p2.add_argument("--render", action="store_true", default=True)
    p2.add_argument("--no-render", dest="render", action="store_false")
    p2.add_argument("--dump-titles", action="store_true"); p2.set_defaults(fn=cmd_save)
    p3 = sub.add_parser("posted"); p3.add_argument("--record", required=True); p3.add_argument("--date", required=True)
    p3.add_argument("--likes", type=int); p3.add_argument("--collects", type=int); p3.add_argument("--comments", type=int)
    p3.set_defaults(fn=cmd_posted)
    p4 = sub.add_parser("stats"); p4.set_defaults(fn=cmd_stats)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
