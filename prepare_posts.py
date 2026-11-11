#!/usr/bin/env python3
"""把准备好的成品（正文/标签/封面）写进飞书「内容生产」表。

用法：
  python3 prepare_posts.py posts_20261111.json            # 出图 + 上传附件 + 写字段
  python3 prepare_posts.py posts_20261111.json --dry-run  # 只出图，不碰表
  python3 prepare_posts.py posts_20261111.json --skip-upload  # 不重传附件（避免重复）

写入字段：正文 / 标签 / 状态=待发 / 计划发布 / 已发布=false / 封面图(附件)
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "MUYVbTkkiawQkIssZxRcAAxHnGf"
TABLE = "tblF23HauKZqae65"
LARK = "lark-cli"
TMP = Path("/tmp")  # lark-cli 拒绝 /root 下路径


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(TMP), **kw)
    if r.returncode != 0:
        sys.exit(f"失败: {' '.join(cmd[:4])}…\nSTDOUT:{r.stdout[-1200:]}\nSTDERR:{r.stderr[-1200:]}")
    return r.stdout


def fetch_rows():
    raw = run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE])
    man = json.loads(raw[raw.find("{"):])
    return [json.loads(l) for l in Path(man["record_file"]).read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-upload", action="store_true")
    a = ap.parse_args()

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    ts = time.strftime("%m%d-%H%M")
    rows = {r["record_id"]: r for r in fetch_rows()}

    report = []
    for i, p in enumerate(spec["posts"], 1):
        rid = p["record_id"]
        if rid not in rows:
            sys.exit(f"记录不存在: {rid}")
        slug = f"p{i}"
        imgs = []
        for tpl, data in p["cover"].items():
            f = TMP / f"{slug}-{tpl}.json"
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            out = run([sys.executable, str(ROOT / "render_cover.py"), "--template", tpl,
                       "--data-file", str(f), "--outdir", str(ROOT / "out" / "covers"),
                       "--name", f"发布{ts}-{slug}-{tpl}"])
            imgs.append(out.strip().splitlines()[-1])

        # 上传附件（多张一次带上）
        if not a.dry_run and not a.skip_upload:
            up = TMP / f"upload_{slug}"
            up.mkdir(exist_ok=True)
            local = []
            for k, src in enumerate(imgs):
                dst = up / f"{slug}_{k+1}_{Path(src).name.split('-')[-2]}.png"
                shutil.copy(src, dst)
                local.append(str(dst))
            cmd = [LARK, "base", "+record-upload-attachment", "--base-token", BASE,
                   "--table-id", TABLE, "--record-id", rid, "--field-id", "封面图"]
            for f in local:
                cmd += ["--file", f]
            run(cmd)

        fields = {
            "正文": p["body"],
            "标签": p["tags"],
            "状态": ["待发"],
            "计划发布": p["publish"],
            "已发布": False,
        }
        if not a.dry_run:
            payload = {"update_records": {rid: fields}}
            run([LARK, "base", "+record-batch-update", "--base-token", BASE, "--table-id", TABLE,
                 "--json", json.dumps(payload, ensure_ascii=False)])
        report.append((rid, p["title"], p["publish"], len(imgs)))

    print(f"处理 {len(report)} 条" + ("（dry-run，未写表）" if a.dry_run else ""))
    for rid, title, pub, n in report:
        print(f"  {rid} | {pub} | {n} 张图 | {title}")

    if not a.dry_run:
        rows2 = {r["record_id"]: r for r in fetch_rows()}
        print("\n回读校验：")
        for rid, title, pub, n in report:
            r = rows2[rid]
            st = (r.get("状态") or [None])[0]
            body_len = len(r.get("正文") or "")
            att = len(r.get("封面图") or [])
            ok = st == "待发" and body_len > 100 and att > 0
            print(f"  {'✓' if ok else '⚠'} {rid} 状态={st} 正文{body_len}字 附件{att}张 计划={r.get('计划发布')} 已发布={r.get('已发布')}")
        print("\n表: https://my.feishu.cn/base/%s?table=%s" % (BASE, TABLE))


if __name__ == "__main__":
    main()
