#!/usr/bin/env python3
"""从飞书「内容生产」表生成 site/data.json（含封面拷贝）。

用法：python3 site/build_data.py
封面统一改名为 cover_<record_id>.png —— ASCII 名，避免 GitHub Pages 对中文文件名
百分号编码处理不一致，导致 <img> 拿不到图（curl 200 但浏览器失败）。
"""
import json, glob, os, re, shutil, subprocess

BASE = "MUYVbTkkiawQkIssZxRcAAxHnGf"
TABLE = "tblF23HauKZqae65"
SITE = os.path.dirname(os.path.abspath(__file__))
COVERS_SRC = os.path.join(os.path.dirname(SITE), "out", "covers")


def lark(*args):
    r = subprocess.run(["lark-cli", *args], capture_output=True, text=True, cwd="/tmp", timeout=180)
    raw = r.stdout
    i = raw.find("{")
    if i < 0:
        raise SystemExit(f"lark-cli 失败: {r.stderr[:300]}")
    return json.loads(raw[i:])


def slug(s):
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", s).strip("_")


def find_cover(title):
    s = slug(title)[:10]
    cands = [c for c in glob.glob(os.path.join(COVERS_SRC, "*-result-*.png")) if slug(os.path.basename(c)).startswith(s)]
    return sorted(cands)[-1] if cands else None


def parse_material(m):
    m = m or ""
    body, tags, cover = m, [], None
    if "\n标签:" in m:
        head, rest = m.split("\n标签:", 1)
        body = head.strip()
        tg = rest.strip()
        if "\n\n封面:" in tg:
            tg, cov = tg.split("\n\n封面:", 1)
            try:
                cover = json.loads(cov.strip())
            except Exception:
                cover = None
        tags = re.findall(r"#[^\s#]+", tg)
    return body, tags, cover


def main():
    meta = lark("base", "+record-list", "--base-token", BASE, "--table-id", TABLE)
    recs = [json.loads(l) for l in open(meta["record_file"]) if l.strip()]

    outdir = os.path.join(SITE, "covers")
    os.makedirs(outdir, exist_ok=True)
    for old in glob.glob(os.path.join(outdir, "*.png")):
        os.remove(old)

    items = []
    for rec in recs:
        rid = rec["record_id"]
        body, tags, _ = parse_material(rec.get("素材"))
        img = None
        src = find_cover(rec["标题"])
        if src:
            name = f"cover_{rid}.jpg"
            dst = os.path.join(outdir, name)
            try:
                from PIL import Image
                im = Image.open(src).convert("RGB")
                im = im.resize((1242, 1656), Image.LANCZOS)
                im.save(dst, "JPEG", quality=88, optimize=True, progressive=True)
            except Exception:
                shutil.copy(src, dst)
            img = f"covers/{name}"
        items.append({
            "id": rid,
            "title": rec["标题"],
            "status": (rec.get("状态") or ["选题"])[0],
            "type": (rec.get("类型") or ["引流"])[0],
            "score": rec.get("评分"),
            "plan": (rec.get("计划发布") or "")[:10],
            "likes": rec.get("点赞") or 0,
            "collects": rec.get("收藏") or 0,
            "comments": rec.get("评论") or 0,
            "body": body,
            "tags": tags,
            "cover": img,
            "material_ready": bool(rec.get("素材到位")),
            "note": rec.get("备注") or "",
        })

    json.dump(items, open(os.path.join(SITE, "data.json"), "w"), ensure_ascii=False, indent=1)
    print(f"条目 {len(items)} | 封面 {sum(1 for i in items if i['cover'])}")


if __name__ == "__main__":
    main()
