#!/usr/bin/env python3
"""hiviz report renderer — funnel markdown -> self-contained HTML view.

Parses the format-contract structure (literal section headers, pipe-table rows,
executive stat line) and renders one portable HTML file: inline CSS, no
network, no dependencies. The HTML is a VIEW — regenerate, never hand-edit.
Unrecognized structure falls back to a monospace dump, so nothing is lost.
"""
from __future__ import annotations

import argparse
import html as H
import re
import sys
from pathlib import Path

STYLE = """
body{font:14px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;margin:0;background:#0f1115;color:#d7dce3;padding:32px}
.wrap{max-width:980px;margin:0 auto}
h1{font-size:18px;color:#e8ecf1;margin:0 0 4px}
h2{font-size:15px;margin:28px 0 8px;padding:6px 10px;border-radius:6px;background:#1a1f27;border-left:4px solid #555}
h2.act{border-color:#e5484d}.h2y{border-color:#e5a13d}.h2k{border-color:#4a5560}
h2.apx{border-color:#333;color:#8a93a0}
.exec{font:600 20px/1.4 ui-monospace,Consolas,monospace;background:#161b23;border:1px solid #262d38;border-radius:8px;padding:14px 18px;margin:14px 0;color:#e8ecf1}
.exec .r{color:#e5484d}.exec .y{color:#e5a13d}.exec .k{color:#7d8794}
table{border-collapse:collapse;width:100%;margin:6px 0 14px;font-size:13px}
th,td{padding:5px 8px;border:1px solid #262d38;text-align:left;vertical-align:top}
th{background:#161b23;color:#8a93a0;font-weight:600}
td.id{font-family:ui-monospace,Consolas,monospace;color:#7d8794;white-space:nowrap}
td.verb{font-family:ui-monospace,Consolas,monospace;color:#e5a13d;white-space:nowrap}
pre,code{font:12px/1.5 ui-monospace,Consolas,monospace}
pre{background:#161b23;border:1px solid #262d38;border-radius:6px;padding:10px;overflow-x:auto;color:#aab3bd}
blockquote{border-left:3px solid #e5a13d;margin:8px 0;padding:2px 12px;color:#aab3bd}
details{margin:8px 0}summary{cursor:pointer;color:#8a93a0}
.foot{margin-top:28px;color:#5b6570;font-size:11px}
"""


def colorize_exec(line: str) -> str:
    s = H.escape(line)
    s = re.sub(r"(🔴[^·]*·)", r'<span class="r">\1</span>', s)
    s = re.sub(r"(🟡[^·]*·)", r'<span class="y">\1</span>', s)
    s = re.sub(r"(⚪[^·]*·)", r'<span class="k">\1</span>', s)
    return s


def table_html(rows: list[list[str]]) -> str:
    head, *body = rows
    out = ["<table><tr>" + "".join(f"<th>{H.escape(c)}</th>" for c in head) + "</tr>"]
    for r in body:
        cells = []
        for i, c in enumerate(r):
            cls = "id" if (i == 0 and head[0].lower() in ("id",)) else \
                  ("verb" if c.strip() in ("delete", "rewrite", "keep", "disable", "merge", "verify") else "")
            cells.append(f'<td class="{cls}">{H.escape(c)}</td>')
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def render(md: str, title: str) -> str:
    out, in_code, table, open_details = [], False, [], False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                out.append("</pre>"); in_code = False
            else:
                out.append("<pre>"); in_code = True
            continue
        if in_code:
            out.append(H.escape(line)); continue
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            table.append(cells); continue
        if table:
            out.append(table_html(table)); table = []
        if not s:
            continue
        if s.startswith("## "):
            name = s[3:]
            cls = {"🔴": "act", "🟡": "h2y", "⚪": "h2k", "Appendix": "apx"}.get(name[0:1] if not name.startswith("Appendix") else "Appendix", "")
            if open_details:
                out.append("</div></details>")
                open_details = False
            if name.startswith(("⚪", "Appendix")):
                out.append(f'<details><summary><h2 class="{cls}" style="display:inline">{H.escape(name)}</h2></summary><div>')
                open_details = True
            else:
                out.append(f'<h2 class="{cls}">{H.escape(name)}</h2>')
            continue
        if s.startswith("# "):
            out.append(f"<h1>{H.escape(s[2:])}</h1>"); continue
        if re.match(r"^🔴.*shed", s) or " act now · " in s:
            out.append(f'<div class="exec">{colorize_exec(s)}</div>'); continue
        if s.startswith("> "):
            out.append(f"<blockquote>{H.escape(s[2:])}</blockquote>"); continue
        out.append(f"<p>{H.escape(s)}</p>")
    if table:
        out.append(table_html(table))
    if in_code:
        out.append("</pre>")
    if open_details:
        out.append("</div></details>")
    body = "".join(out)
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{H.escape(title)}</title><style>{STYLE}</style></head>"
            f"<body><div class='wrap'>{body}"
            "<div class='foot'>generated view — regenerate, never hand-edit · hiviz</div>"
            "</div></body></html>")


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz report renderer")
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    src = Path(a.md)
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    html = render(src.read_text(encoding="utf-8"), src.stem)
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"html view: {a.out} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
