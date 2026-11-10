# sidehustle-pipeline

把「选题 → 草稿 → 封面 → 发布 → 回填 → 复盘」里能自动化的四段做成脚本，剩下两段（给素材、点发布）留给人。

配套：飞书多维表格 base `MUYVbTkkiawQkIssZxRcAAxHnGf`，表「内容生产」`tblF23HauKZqae65`。

## 为什么不是全自动

- **小红书没有开放发布 API**：内容只能人工点发布，这条自动化不了。
- **素材必须是真的**：截图 + 场景/做法/效果三句话只能你给。AI 编出来的效果数字会让你三个月后归因错误。
- 所以设计是：**你丢素材 → 30 分钟拿到可发成品**，不是无人值守。

## 三条命令

```bash
python3 make_draft.py stats                  # 池子体检：水位、卡在哪
python3 make_draft.py next --limit 3         # 挑出能开工的选题（素材到位才放行）
python3 make_draft.py save --file draft.json --date 2026-11-12   # 草稿写回表 + 出 3 张封面
python3 make_draft.py posted --record recXXX --date 2026-11-12 --likes 12 --collects 8 --comments 3
python3 weekly_review.py                     # 周复盘（cron 每周日 20:00 自动跑）
```

只出封面：

```bash
python3 render_cover.py --template all --data-file spec.json --name 选题名
# → out/covers/选题名-{result,list,compare}-时间戳.png （1242×1656，2x = 2484×3312）
```

## 一周怎么用

| 时间 | 谁 | 做什么 |
|---|---|---|
| 周一 | 你 | 挑 1-2 条选题，按库里的备注把素材补进「素材」字段，勾上「素材到位」 |
| 周中 | 我 | `next` 取题 → 出 10 标题 + 正文 + 标签 + 封面 → `save` 写回，状态到「待做图」 |
| 自己定 | 你 | 看图、改字、发小红书（一次只改一个变量：封面或标题） |
| 发完 | 你 | 告诉我赞藏评，我 `posted` 回填 |
| 周日 20:00 | 自动 | `weekly_review.py` 出周报，只给 1-2 条下周动作 |

## draft.json 格式

```json
{
  "record_id": "recXXX",
  "title": "最终用的标题",
  "titles": ["备选1", "备选2"],
  "body": "正文，300 字内",
  "tags": ["#飞书", "#多维表格"],
  "cover": {"template": "all", "tag": "飞书 · 多维表格", "title": ["第一行", "第二行"],
            "big": "60%→95%", "sub": "一句解释",
            "items": ["清单条目1", "清单条目2"],
            "bad_lab": "以前", "bad_num": "2 小时", "bad_desc": "...",
            "good_lab": "现在", "good_num": "0 干预", "good_desc": "..."}
}
```

`template` 三选一：`result`（有数字）/ `list`（可列条目）/ `compare`（前后对比）/ `all`（一次三张）。
`title` 里的 `*词*` 在 list 模板中渲染成强调色。

## 封面排版规则（别踩）

- 字号由 `fit_width()` 按视觉宽度算（中文 1em、ASCII 0.55em，可用宽 1050px），**不要改回固定字号**——长文案会断行。
- `capture_screenshot` 那套只有浏览器里才有；这里走 `chrome --headless --screenshot`，无需 Playwright。
- 出图后必须看图确认没溢出再发（文字换行是最常见的翻车点）。

## 文件

```
render_cover.py      模板 → PNG（自动缩字号）
make_draft.py        选题筛选 / 草稿写回 / 发后回填 / 体检
weekly_review.py     周复盘
templates/           3 套 3:4 封面模板
out/covers/          产出图（git 忽略）
```
