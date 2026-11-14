#!/usr/bin/env python3
"""生成副业工作台数据：待办 / 内容 / 项目 / 定时任务 → site/workbench/data.json"""
import json, os, subprocess, glob, datetime

BASE = "MUYVbTkkiawQkIssZxRcAAxHnGf"
TBL_TODO = "tblZmUxPbAnXfkTy"
TBL_CONTENT = "tblF23HauKZqae65"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data.json")


def lark(*args):
    r = subprocess.run(["lark-cli", *args], capture_output=True, text=True, cwd="/tmp", timeout=180)
    raw = r.stdout
    i = raw.find("{")
    if i < 0:
        return []
    meta = json.loads(raw[i:])
    f = meta.get("record_file")
    if not f or not os.path.exists(f):
        return []
    return [json.loads(l) for l in open(f) if l.strip()]


def today():
    return datetime.date.today()


def date_of(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except Exception:
        return None


def todos():
    rows = lark("base", "+record-list", "--base-token", BASE, "--table-id", TBL_TODO)
    out = []
    for r in rows:
        st = (r.get("状态") or ["待办"])[0]
        if st in ("已完成", "已取消"):
            continue
        out.append({
            "title": r.get("事项") or "",
            "status": st,
            "prio": (r.get("优先级") or [""])[0],
            "due": (r.get("截止日期") or "")[:10],
            "tags": r.get("标签") or [],
        })
    t = today()
    for x in out:
        d = date_of(x["due"])
        x["days"] = (d - t).days if d else None
    out.sort(key=lambda x: (x["days"] is None, x["days"] if x["days"] is not None else 999))
    return out


def contents():
    rows = lark("base", "+record-list", "--base-token", BASE, "--table-id", TBL_CONTENT)
    items = []
    for r in rows:
        items.append({
            "title": r.get("标题") or "",
            "status": (r.get("状态") or ["选题"])[0],
            "type": (r.get("类型") or [""])[0],
            "score": r.get("评分"),
            "plan": (r.get("计划发布") or "")[:10],
            "ready": bool(r.get("素材到位")),
            "likes": r.get("点赞") or 0,
        })
    order = ["待发", "待做图", "待写", "选题", "已发", "复盘"]
    counts = {k: sum(1 for i in items if i["status"] == k) for k in order}
    focus = [i for i in items if i["status"] in ("待发", "待做图", "待写")]
    focus.sort(key=lambda x: -((x["score"] or 0)))
    return {"counts": counts, "total": len(items), "focus": focus[:6],
            "ready": sum(1 for i in items if i["ready"])}


def projects():
    out = []
    for d in sorted(glob.glob("/root/work/*/")):
        name = os.path.basename(d.rstrip("/"))
        try:
            log = subprocess.run(["git", "-C", d, "log", "-1", "--format=%cs|%s"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            dirty = subprocess.run(["git", "-C", d, "status", "--porcelain"],
                                   capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            continue
        if not log:
            continue
        cdate, _, subj = log.partition("|")
        days = (today() - datetime.date.fromisoformat(cdate)).days
        out.append({"name": name, "date": cdate, "days": days,
                    "subject": subj[:60], "dirty": len(dirty.splitlines())})
    out.sort(key=lambda x: -x["days"])
    return out


def jobs():
    p = "/root/.hermes/cron/jobs.json"
    if not os.path.exists(p):
        return []
    d = json.load(open(p))
    raw = d.get("jobs", d)
    items = raw.values() if isinstance(raw, dict) else raw
    out = []
    for j in items:
        if not isinstance(j, dict):
            continue
        if j.get("deleted"):
            continue
        sch = j.get("schedule")
        if isinstance(sch, dict):
            sch = sch.get("display") or sch.get("expr") or sch.get("kind") or ""
        out.append({
            "name": j.get("name") or j.get("job_id"),
            "schedule": str(sch or ""),
            "enabled": j.get("enabled", True),
            "last": (j.get("last_status") or "").lower(),
            "next": (j.get("next_run_at") or "")[:16].replace("T", " "),
        })
    out.sort(key=lambda x: (x["last"] != "failed", x["name"]))
    return out


def main():
    data = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": str(today()),
        "todos": todos(),
        "content": contents(),
        "projects": projects(),
        "jobs": jobs(),
    }
    json.dump(data, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"待办 {len(data['todos'])} | 内容 {data['content']['total']} | 项目 {len(data['projects'])} | 任务 {len(data['jobs'])}")


if __name__ == "__main__":
    main()