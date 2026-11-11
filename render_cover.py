#!/usr/bin/env python3
"""封面批量渲染：模板 + 文案 → 1242x1656 (2x = 2484x3312) PNG。

用法：
  # 单张
  python3 render_cover.py --template result --data '{"tag":"飞书 · 多维表格","title":["团队交任务","准时率"],"big":"60%→95%","sub":"只加了一个自动催办"}' -o out.png

  # 一次出 3 种版式（同一份内容，能自动映射的槽位自动补）
  python3 render_cover.py --template all --data-file spec.json --outdir out/covers --name 选题slug

  # 批量：spec.json = {"covers":[{...},{...}]}，每项可带 "template"/"name"
  python3 render_cover.py --batch covers.json --outdir out/covers

退出码非 0 表示渲染失败（调用方别盲发图）。
"""
import argparse
import glob
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TPL_DIR = ROOT / "templates"
DEFAULT_OUT = ROOT / "out" / "covers"
W, H, SCALE = 1242, 1656, 2


def find_chrome() -> str:
    env = os.environ.get("CHROME_BIN")
    if env and Path(env).exists():
        return env
    cands = sorted(glob.glob("/root/.hermes/tools/chromium-*/chrome-linux64/chrome"))
    cands += ["/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]
    for c in cands:
        if Path(c).exists():
            return c
    sys.exit("找不到 Chrome/Chromium，请设置 CHROME_BIN")


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=False)


def _title_parts(data):
    t = data.get("title")
    if isinstance(t, str):
        parts = [p for p in t.split("\n")]
    elif isinstance(t, list):
        parts = [str(p) for p in t]
    else:
        parts = [""]
    return parts or [""]


def _title_html(parts, allow_em=True) -> str:
    out = []
    for p in parts:
        p = esc(p)
        if allow_em:  # 允许用 *词* 标强调色
            p = re.sub(r"\*(.+?)\*", r"<em>\1</em>", p)
        out.append(p)
    return "<br>".join(out)


def _len(s: str) -> int:
    """按视觉宽度估字数：中文 1，ASCII 0.55。"""
    return sum(0.55 if ord(c) < 128 else 1 for c in s)


AVAIL_W = W - 96 * 2  # 左右各 96px 内边距后的可用宽度


def fit_width(text, base, avail=AVAIL_W, min_size=40, safety=0.94):
    """按视觉宽度算字号：中文 1em，ASCII 约 0.55em。宁可小一点，不要断行。"""
    n = _len(text or "")
    if n <= 0:
        return base
    return max(min_size, min(base, int(avail * safety / n)))


def fit_title(parts, base, min_size=56):
    """标题每行独立算宽度，取最紧的那个；超过一行时行高收紧。"""
    size = min(fit_width(p, base, min_size=min_size) for p in parts) if parts else base
    lh = 1.24 if size >= base * 0.85 else 1.16
    return size, lh


def build(name, data: dict) -> str:
    tpl_path = TPL_DIR / f"cover_{name}.html"
    if not tpl_path.exists():
        sys.exit(f"没有模板 {tpl_path}")
    tpl = tpl_path.read_text(encoding="utf-8")
    parts = _title_parts(data)
    slots = {
        "tag": esc(data.get("tag", "")),
        "foot_left": esc(data.get("foot_left", "做法在正文")),
        "foot_right": esc(data.get("foot_right", "P2 →")),
    }

    if name == "result":
        size, lh = fit_title(parts, 104)
        big = data.get("big", "")
        sub = data.get("sub", "")
        slots.update(
            title_html=_title_html(parts, allow_em=False),
            title_size=size,
            title_lh=lh,
            big=esc(big),
            big_size=fit_width(big, 196, min_size=88),
            sub=esc(sub),
            sub_size=fit_width(sub, 54, min_size=34),
        )
    elif name == "list":
        items = [str(x) for x in (data.get("items") or [])]
        if not items:
            sys.exit("list 模板需要 items 数组")
        size, lh = fit_title(parts, 108)
        n = len(items)
        item_size = 50 if n <= 5 else (44 if n == 6 else 38)
        item_gap = 26 if n <= 5 else 20
        item_size = min(item_size, min(fit_width(t, item_size, avail=AVAIL_W - 92, min_size=28) for t in items))
        rows = "\n".join(
            f'      <div class="item" style="font-size:{item_size}px"><span class="num" '
            f'style="font-size:{int(item_size*0.76)}px">{i:02d}</span><span>{esc(t)}</span></div>'
            for i, t in enumerate(items, 1)
        )
        slots.update(
            title_html=_title_html(parts),
            title_size=size,
            title_lh=lh,
            items=rows,
            item_gap=item_gap,
        )
    elif name == "compare":
        size, lh = fit_title(parts, 100)
        nums = [data.get("bad_num", ""), data.get("good_num", "")]
        num_size = min(fit_width(x, 86, avail=423, min_size=44) for x in nums)
        slots.update(
            title_html=_title_html(parts, allow_em=False),
            title_size=size,
            title_lh=lh,
            bad_lab=esc(data.get("bad_lab", "以前")),
            bad_num=esc(nums[0]),
            bad_desc=esc(data.get("bad_desc", "")),
            good_lab=esc(data.get("good_lab", "现在")),
            good_num=esc(nums[1]),
            good_desc=esc(data.get("good_desc", "")),
            num_size=num_size,
        )
    else:
        sys.exit(f"未知模板 {name}")

    for k, v in slots.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    left = re.findall(r"\{\{[a-z_]+\}\}", tpl)
    if left:
        sys.exit(f"模板还有未填充占位符: {set(left)}")
    return tpl


def render(name, data, out_path: Path) -> Path:
    chrome = find_chrome()
    out_path = Path(out_path).expanduser().resolve()  # 相对路径会让 as_uri() 报错
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_html = out_path.parent / f".{out_path.stem}.html"
    tmp_html.write_text(build(name, data), encoding="utf-8")
    cmd = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--force-device-scale-factor=%d" % SCALE,
        "--window-size=%d,%d" % (W, H),
        "--virtual-time-budget=3000",
        "--screenshot=%s" % out_path,
        tmp_html.as_uri(),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if not out_path.exists() or out_path.stat().st_size < 5000:
        sys.exit(f"渲染失败 {name}: rc={r.returncode}\n{r.stderr[-1500:]}")
    tmp_html.unlink(missing_ok=True)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="result", choices=["result", "list", "compare", "all"])
    ap.add_argument("--data")
    ap.add_argument("--data-file")
    ap.add_argument("--batch")
    ap.add_argument("-o", "--out")
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    ap.add_argument("--name", default="cover")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff-]+", "_", a.name)[:60] or "cover"
    ts = time.strftime("%Y%m%d-%H%M%S")

    if a.batch:
        spec = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        made = []
        for i, item in enumerate(spec.get("covers", []), 1):
            tpl = item.pop("template", "result")
            nm = item.pop("name", f"{slug}-{i}")
            made.append(render(tpl, item, outdir / f"{nm}-{tpl}-{ts}.png"))
        print(json.dumps([str(p) for p in made], ensure_ascii=False, indent=1))
        return

    if a.data_file:
        data = json.loads(Path(a.data_file).read_text(encoding="utf-8"))
    elif a.data:
        data = json.loads(a.data)
    else:
        sys.exit("需要 --data / --data-file / --batch")

    if a.template == "all":
        made = [render(t, data, outdir / f"{slug}-{t}-{ts}.png") for t in ("result", "list", "compare")]
    else:
        out = Path(a.out) if a.out else outdir / f"{slug}-{a.template}-{ts}.png"
        made = [render(a.template, data, out)]
    for p in made:
        print(p)


if __name__ == "__main__":
    main()
