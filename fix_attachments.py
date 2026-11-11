#!/usr/bin/env python3
"""把已上传的封面附件重命名成可读名字（01-result / 02-list / 03-compare）。

做法是 remove 旧 token 再按新文件名重传（飞书附件名不可原地改）。
用法：python3 fix_attachments.py posts_20261111.json
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "MUYVbTkkiawQkIssZxRcAAxHnGf"
TABLE = "tblF23HauKZqae65"
LARK = "lark-cli"
TMP = Path("/tmp")
LABEL = {"result": "01-result-结果型", "list": "02-list-清单型", "compare": "03-compare-对比型"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(TMP))
    if r.returncode != 0:
        sys.exit(f"失败 {' '.join(cmd[:3])}\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
    return r.stdout


def rows():
    raw = run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE])
    man = json.loads(raw[raw.find("{"):])
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in Path(man["record_file"]).read_text(encoding="utf-8").splitlines() if l.strip()}


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cur = rows()
    for i, p in enumerate(spec["posts"], 1):
        rid = p["record_id"]
        atts = cur[rid].get("封面图") or []
        if not atts:
            print(f"跳过 {rid}: 没有附件")
            continue
        # 1) 删旧的
        cmd = [LARK, "base", "+record-remove-attachment", "--base-token", BASE, "--table-id", TABLE,
               "--record-id", rid, "--field-id", "封面图", "--yes"]
        for a in atts:
            cmd += ["--file-token", a["file_token"]]
        run(cmd)
        # 2) 按名字重传（同一模板可能存在多批出图，取时间戳最新的那张）
        allpng = sorted((ROOT / "out" / "covers").glob(f"发布*-p{i}-*.png"))
        latest = {}
        for s in allpng:
            tpl = s.name.rsplit("-", 3)[1]
            latest[tpl] = s  # sorted 升序，后者覆盖前者 = 最新
        srcs = [latest[t] for t in ("result", "list", "compare") if t in latest]
        up = TMP / f"rename_p{i}"
        up.mkdir(exist_ok=True)
        cmd = [LARK, "base", "+record-upload-attachment", "--base-token", BASE, "--table-id", TABLE,
               "--record-id", rid, "--field-id", "封面图"]
        for s in srcs:
            tpl = s.name.rsplit("-", 3)[1]
            dst = up / f"{LABEL.get(tpl, tpl)}.png"
            shutil.copy(s, dst)
            cmd += ["--file", str(dst)]
        run(cmd)
        print(f"{rid}: 重命名 {len(srcs)} 张")

    cur2 = rows()
    print("\n校验：")
    for p in spec["posts"]:
        r = cur2[p["record_id"]]
        names = [a["name"] for a in (r.get("封面图") or [])]
        print(f"  {p['record_id']} {len(names)} 张: {names}")


if __name__ == "__main__":
    main()
