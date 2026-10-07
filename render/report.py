#!/usr/bin/env python3
"""hiviz report renderer — funnel markdown -> self-contained HTML view and terminal summary.

Parses the format contract (literal section headers, pipe-table rows, executive stat line)
and renders one portable HTML file: inline CSS + JS, no network, no dependencies. The decision
sections (🔴 Act now, 🟡 Your call) become rows you decide on (yes / no / keep / as-condition),
batch by category and export as decisions.md; ⚪ Kept safe is folded; nothing is pre-decided.
Older reports (4 columns: no `where` / `B`) still render. Unrecognized structure falls back to
a plain markdown view, so nothing is lost. The HTML is a VIEW — regenerate, never hand-edit.

  report.py --md report.md --out report.html     HTML view
  report.py --md report.md --summary             terminal summary (human format)
"""
from __future__ import annotations

import argparse
import hashlib
import html as H
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvfmt  # noqa: E402

STYLE = """
:root{--bg:#0f1115;--panel:#161b23;--line:#262d38;--txt:#d7dce3;--mut:#8a93a0;--dim:#5b6570;
--red:#e5484d;--amb:#e5a13d;--grn:#46a758;--cyn:#4fb3d9;--yel:#d9c24f}
*{box-sizing:border-box}
body{font:14px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;margin:0;background:var(--bg);color:var(--txt);padding:0 32px 48px}
.wrap{max-width:1040px;margin:0 auto}
h1{font-size:18px;color:#e8ecf1;margin:20px 0 4px}
h2{font-size:15px;margin:28px 0 8px;padding:6px 10px;border-radius:6px;background:#1a1f27;border-left:4px solid #555}
h2.act{border-color:var(--red)}.h2y{border-color:var(--amb)}.h2k{border-color:#4a5560}
h2.apx{border-color:#333;color:var(--mut)}
.exec{font:600 16px/1.4 ui-monospace,Consolas,monospace;color:#e8ecf1}
.exec .r{color:var(--red)}.exec .y{color:var(--amb)}.exec .k{color:#7d8794}
table{border-collapse:collapse;width:100%;margin:6px 0 14px;font-size:13px}
th,td{padding:5px 8px;border:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--panel);color:var(--mut);font-weight:600}
td.id{font-family:ui-monospace,Consolas,monospace;color:#7d8794;white-space:nowrap}
td.verb{font-family:ui-monospace,Consolas,monospace;color:var(--amb);white-space:nowrap}
pre,code{font:12px/1.5 ui-monospace,Consolas,monospace}
code{background:#1c222c;padding:0 4px;border-radius:3px}
pre{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px;overflow-x:auto;color:#aab3bd}
blockquote{border-left:3px solid var(--amb);margin:8px 0;padding:2px 12px;color:#aab3bd}
ul.top{margin:8px 0 4px;padding-left:20px}ul.top li{margin:2px 0}
details{margin:8px 0}summary{cursor:pointer;color:var(--mut)}
.foot{margin-top:28px;color:var(--dim);font-size:11px}
.top-bar{position:sticky;top:0;z-index:5;background:rgba(15,17,21,.94);backdrop-filter:blur(6px);
border-bottom:1px solid var(--line);margin:0 -32px;padding:10px 32px 12px}
.top-bar .in{max-width:1040px;margin:0 auto}
.stats{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;margin-top:8px;font-size:12.5px;color:var(--mut)}
.prog{display:inline-flex;align-items:center;gap:8px}
.prog .bar{width:140px;height:8px;border-radius:4px;background:#222a35;overflow:hidden}
.prog .bar i{display:block;height:100%;width:0;background:var(--grn);transition:width .15s}
.stats b{color:var(--txt);font-weight:600}
.ctl{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
button{font:12px/1 -apple-system,'Segoe UI',sans-serif;color:var(--txt);background:#1c222c;border:1px solid #2d3643;
border-radius:5px;padding:6px 10px;cursor:pointer}
button:hover{background:#242c38}button[aria-pressed=true]{background:#2a3442;border-color:#5b6b82}
button:disabled{opacity:.4;cursor:default}
button.go{background:#1f4d33;border-color:#2f7a4f}button.go:hover{background:#25603f}
.sortgrp{display:inline-flex}.sortgrp button{border-radius:0;margin-left:-1px}
.sortgrp button:first-child{border-radius:5px 0 0 5px;margin-left:0}.sortgrp button:last-child{border-radius:0 5px 5px 0}
.lbl{color:var(--dim);margin-right:4px}
.toolbar{display:flex;align-items:center;gap:8px;margin:14px 0 0;font-size:12.5px;color:var(--mut)}
.batch{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px;align-items:center}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--panel);border:1px solid var(--line);
border-radius:6px;padding:4px 8px;font-size:12px;color:var(--mut)}
.chip b{color:var(--txt)}.chip button{padding:3px 8px}
.row{--c:#4a5560;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 18px;padding:10px 12px;margin:8px 0;
background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:8px;scroll-margin-top:110px}
.row.sel{outline:1px solid #5b6b82}
.row[data-d=no],.row[data-d=keep]{opacity:.62}
.row[data-d=yes]{background:#16221b}.row[data-d=cond]{background:#221f14}
.v-delete,.v-disable{--c:var(--red)}.v-rewrite{--c:var(--amb)}.v-merge{--c:var(--cyn)}.v-verify{--c:var(--yel)}.v-keep{--c:var(--grn)}
.meta{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;font-size:12.5px}
.meta .id{font:600 12px ui-monospace,Consolas,monospace;color:#9aa4b1}
.meta .verb{font:600 12.5px ui-monospace,Consolas,monospace;color:var(--c)}
.meta .cat{color:var(--mut);background:#1c222c;border-radius:10px;padding:0 8px;font-size:11.5px}
.meta .where{font:12px ui-monospace,Consolas,monospace;color:#7fa6d9}
.eff{display:flex;align-items:center;gap:8px;font:12px ui-monospace,Consolas,monospace;color:var(--mut);justify-content:flex-end}
.eff .bar{width:90px;height:6px;border-radius:3px;background:#222a35;overflow:hidden}
.eff .bar i{display:block;height:100%;background:var(--c)}
.body{grid-column:1}.dec{grid-column:2;grid-row:2;display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.q{margin:4px 0;white-space:pre-wrap;word-break:break-word;background:#12161d;border:1px solid #232a35;color:#c6ceda;padding:6px 10px}
.why{color:var(--mut);font-size:13px}.why .ev{color:var(--dim);font-size:11.5px;margin-right:6px}
.seg{display:inline-flex}.seg button{border-radius:0;margin-left:-1px;min-width:46px}
.seg button:first-child{border-radius:5px 0 0 5px;margin-left:0}.seg button:last-child{border-radius:0 5px 5px 0}
.seg button[aria-pressed=true][data-v=yes]{background:#1f4d33;border-color:#2f7a4f}
.seg button[aria-pressed=true][data-v=no]{background:#4d2326;border-color:#7a3b3f}
.seg button[aria-pressed=true][data-v=cond]{background:#4d4020;border-color:#7a6a35}
input.note{display:none;width:240px;font:12px ui-monospace,Consolas,monospace;background:#12161d;color:var(--txt);
border:1px solid #2d3643;border-radius:5px;padding:5px 8px}.row[data-d=cond] input.note{display:block}
.conf{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:stretch;margin:6px 0}
.conf .side{background:#12161d;border:1px solid #232a35;border-radius:6px;padding:6px 10px;min-width:0}
.conf .side .w{font:11.5px ui-monospace,Consolas,monospace;color:#7fa6d9;margin-bottom:3px}
.conf .side .t{font:12px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-word;color:#c6ceda}
.conf .sw{align-self:center;color:var(--red);font-size:18px}
.safe .row{padding:6px 12px;margin:4px 0}.safe .row .q{margin:2px 0;padding:2px 8px}
.hint{color:var(--dim);font-size:11.5px;margin-top:6px}
#toast{position:fixed;right:20px;bottom:20px;background:#1f4d33;border:1px solid #2f7a4f;color:#e8ecf1;padding:10px 14px;
border-radius:8px;font-size:13px;display:none;max-width:420px}
"""

SCRIPT = r"""
(function(){
var D=JSON.parse(document.getElementById('hv-data').textContent);
var KEY='hiviz:'+D.key,st={};
try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
var $=function(s,r){return(r||document).querySelector(s)},$$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
var rowsEl=$$('.row[data-need]'),byId={};D.rows.forEach(function(r){byId[r.id]=r});
var SHED={delete:1,rewrite:1,merge:1,disable:1};
function fmtB(n){return n>=1024?(n/1024).toFixed(1)+' KB':n+' B'}
function save(){try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
function setD(k,v,note){
  if(!v||(st[k]&&st[k].d===v&&note===undefined)){delete st[k]}
  else{st[k]={d:v,n:note!==undefined?note:(st[k]&&st[k].n)||''}}
  save();paint();
}
function match(el,ch){var r=byId[el.dataset.id];return el.dataset.sec===ch.dataset.sec&&r.cat===ch.dataset.cat&&r.verb===ch.dataset.verb&&!st[r.id]}
function paint(){
  var n=0,c={yes:0,no:0,keep:0,cond:0},shed=0;
  rowsEl.forEach(function(el){
    var k=el.dataset.id,s=st[k],r=byId[k];
    el.dataset.d=s?s.d:'';
    $$('.seg button',el).forEach(function(b){b.setAttribute('aria-pressed',s&&s.d===b.dataset.v?'true':'false')});
    var inp=$('input.note',el);if(inp&&s&&inp!==document.activeElement)inp.value=s.n||'';
    if(s){n++;c[s.d]++;if(s.d==='yes'&&SHED[r.verb])shed+=r.b||0}
  });
  var N=rowsEl.length;
  $('#p-bar').style.width=(N?100*n/N:0)+'%';
  $('#p-txt').innerHTML='decided <b>'+n+'/'+N+'</b>';
  $('#p-split').textContent='yes '+c.yes+' · no '+c.no+' · keep '+c.keep+' · cond '+c.cond;
  var sh=$('#p-shed');if(sh&&!sh.hidden)sh.innerHTML='accepted: <b>−'+fmtB(shed)+(D.corpus?' ('+(100*shed/D.corpus).toFixed(1)+'%)':'')+'</b>';
  $$('.chip[data-cat]').forEach(function(ch){
    var k=rowsEl.filter(function(el){return match(el,ch)}).length;
    $('.left',ch).textContent=k;$('button',ch).disabled=!k;
  });
  $('#prev').textContent=exportMd();
}
function esc(s){return String(s==null?'':s).replace(/\|/g,'\\|').replace(/\s*\n\s*/g,' ')}
function exportMd(){
  var out=['# HiViz decisions — exported from the report view','',
   'DECISION: `yes` · `no` · `as-condition: <text>` · `keep`; empty = undecided, leave the line untouched.',''];
  var head=D.cols.map(function(c){return D.labels[c]}).concat(['DECISION']);
  D.sections.forEach(function(sec){
    out.push('## '+sec.title,'','| '+head.join(' | ')+' |','|'+head.map(function(){return '---'}).join('|')+'|');
    D.rows.filter(function(r){return r.sec===sec.key}).forEach(function(r){
      var s=st[r.id],dec=sec.key==='safe'?'keep':!s?'':s.d==='cond'?('as-condition'+(s.n?': '+s.n:'')):s.d;
      out.push('| '+D.cols.map(function(c){return esc(r[c])}).concat([esc(dec)]).join(' | ')+' |');
    });
    out.push('');
  });
  return out.join('\n');
}
function toast(t){var e=$('#toast');e.textContent=t;e.style.display='block';clearTimeout(toast.t);toast.t=setTimeout(function(){e.style.display='none'},4200)}
function sortRows(mode){
  $$('section.sec[data-need]').forEach(function(sec){
    var holder=$('.rows',sec),els=$$('.row',holder);
    els.sort(function(a,b){var x=byId[a.dataset.id],y=byId[b.dataset.id];
      if(mode==='effect')return(y.b||0)-(x.b||0)||x.i-y.i;
      if(mode==='file')return(x.where||'').localeCompare(y.where||'')||x.i-y.i;
      return x.i-y.i});
    els.forEach(function(e){holder.appendChild(e)});
  });
  $$('.sortgrp button').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.s===mode?'true':'false')});
}
document.addEventListener('click',function(e){
  var b=e.target.closest('button');if(!b)return;
  var row=b.closest('.row');
  if(b.dataset.v&&row){var k=row.dataset.id;setD(k,b.dataset.v);if(b.dataset.v==='cond'&&st[k])$('input.note',row).focus()}
  else if(b.dataset.s)sortRows(b.dataset.s);
  else if(b.dataset.batch){var ch=b.closest('.chip');rowsEl.forEach(function(el){if(match(el,ch))st[el.dataset.id]={d:'yes',n:''}});save();paint()}
  else if(b.id==='b-dl'){var blob=new Blob([exportMd()],{type:'text/markdown'}),a=document.createElement('a');
    a.href=URL.createObjectURL(blob);a.download='decisions.md';document.body.appendChild(a);a.click();a.remove();
    toast('Saved decisions.md — put it at .hiviz/decisions.md, then run /hv-apply')}
  else if(b.id==='b-cp'){var t=exportMd();
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(function(){var x=document.createElement('textarea');
      x.value=t;document.body.appendChild(x);x.select();document.execCommand('copy');x.remove()}).then(function(){toast('decisions.md copied')},function(){})}
  else if(b.id==='b-rs'){if(confirm('Clear all decisions in this view?')){st={};save();paint()}}
});
document.addEventListener('input',function(e){var i=e.target;if(i.classList.contains('note')){var k=i.closest('.row').dataset.id;
  if(st[k]){st[k].n=i.value;save();$('#prev').textContent=exportMd()}}});
var cur=-1;
function vis(){return rowsEl.filter(function(x){return x.offsetParent})}
function sel(i){var v=vis();if(!v.length)return;i=Math.max(0,Math.min(v.length-1,i));
  rowsEl.forEach(function(e){e.classList.remove('sel')});v[i].classList.add('sel');v[i].scrollIntoView({block:'nearest'});cur=i}
document.addEventListener('keydown',function(e){
  if(e.target.tagName==='INPUT'||e.metaKey||e.ctrlKey||e.altKey)return;
  var el=vis()[cur];
  if(e.key==='ArrowDown'||e.key==='j'){e.preventDefault();sel(cur+1)}
  else if(e.key==='ArrowUp'){e.preventDefault();sel(cur-1)}
  else if(el&&'ynkc'.indexOf(e.key)>=0){var v={y:'yes',n:'no',k:'keep',c:'cond'}[e.key],k=el.dataset.id;setD(k,v);
    if(v==='cond'&&st[k]){e.preventDefault();$('input.note',el).focus()}}
});
sortRows('effect');paint();
})();
"""

LABELS = {"id": "id", "where": "where", "line": "line", "why": "why", "b": "B", "verb": "→ verb"}
VERBS = ("delete", "rewrite", "keep", "disable", "merge", "verify")
SEC_KEY = {"🔴": "act", "🟡": "call", "⚪": "safe"}


# ------------------------------------------------------------------ parsing
def split_row(s: str) -> list[str]:
    """Pipe-table row -> cells; honors `\\|` (a literal pipe inside a cell)."""
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        if s[i] == "\\" and s[i + 1:i + 2] == "|":
            cur.append("|")
            i += 2
            continue
        if s[i] == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(s[i])
        i += 1
    cells.append("".join(cur).strip())
    return cells


def unwrap(cell: str) -> str:
    """Drop the one pair of backticks a model wraps around a quoted line."""
    m = re.match(r"^(`+)\s?(.*?)\s?\1$", cell.strip(), re.S)
    return m.group(2) if m else cell.strip()


def split_why(why: str) -> tuple[str, str, str]:
    """-> (category, evidence, reason). Legacy `fact:` was an evidence prefix, not a category."""
    cat, ev, rest = "", "", why.strip()
    m = re.match(r"^\[INFERENCE\]\s*", rest)
    if m:
        return "", "inference", rest[m.end():]
    m = re.match(r"^([A-Za-z0-9][\w%\-]{1,24}):\s*(.*)$", rest, re.S)
    if m:
        cat, rest = m.group(1).lower(), m.group(2)
    if cat == "fact":
        cat, ev = "", "fact"
    m = re.match(r"^\[INFERENCE\]\s*", rest)
    if m:
        ev, rest = "inference", rest[m.end():]
    m = re.match(r"^fact:\s*", rest)
    if m:
        ev, rest = "fact", rest[m.end():]
    return cat, ev, rest


def split_loc(loc: str) -> tuple[str, str]:
    m = re.match(r"^(.*?):(\d+(?:-\d+)?)$", loc.strip())
    return (m.group(1), m.group(2)) if m else (loc.strip(), "")


@dataclass
class Row:
    id: str
    sec: str
    where: str
    line: str
    why: str
    b: int | None
    verb: str
    i: int = 0
    cat: str = ""
    ev: str = ""
    decision: str = ""     # the DECISION column of an exported / filled decisions.md
    reason: str = ""
    other: str = ""        # side B of a conflict: location
    other_q: str = ""      # side B of a conflict: quote
    rest: str = ""         # reason without the side-B quote

    @property
    def conflict(self) -> bool:
        return bool(self.other) or self.cat == "conflict"


def parse_rows(head: list[str], body: list[list[str]], sec: str) -> list[Row]:
    # "line ≤60 chars", "→ verb", "#" … -> the first word; models copy the grammar template into the header
    low = [(re.match(r"[a-z]+", re.sub(r"^[^a-z]+", "", h.lower())) or re.match(r"", h)).group(0) for h in head]
    ix = {}
    for k, names in (("id", ("id",)), ("where", ("where", "file", "location")), ("line", ("line",)),
                     ("why", ("why",)), ("b", ("b", "bytes", "size")), ("verb", ("verb",)), ("decision", ("decision",))):
        for j, h in enumerate(low):
            if h in names:
                ix[k] = j
                break
    if "id" not in ix and head:
        ix["id"] = 0
    clean = lambda c: re.sub(r"^[→>\-\s]+", "", re.sub(r"[`*]", "", c)).strip().lower()
    if "verb" not in ix and body:   # header says "→" or "action": take the column whose cells are verbs
        width = max(len(c) for c in body)
        scored = [(sum(clean(c[j]) in VERBS for c in body if j < len(c)), j) for j in range(width)]
        best = max(scored, default=(0, 0))
        if best[0] * 2 >= len(body):
            ix["verb"] = best[1]
    rows = []
    for n, cells in enumerate(body):
        def g(k: str, cells: list[str] = cells) -> str:
            return cells[ix[k]] if k in ix and ix[k] < len(cells) else ""
        digits = re.sub(r"[^\d]", "", g("b"))
        verb = clean(g("verb"))   # models copy the header's arrow into the cell
        r = Row(id=g("id"), sec=sec, where=g("where"), line=g("line"), why=g("why"),
                b=int(digits) if digits else None, verb=verb, i=n)
        r.decision = g("decision")
        r.cat, r.ev, r.reason = split_why(r.why)
        # models wrap paths in backticks / bold: `/a/AGENTS.md:13` ⇄ `/b/SKILL.md:9`
        parts = [p.strip().strip("`*").strip() for p in re.split(r"\s*⇄\s*", r.where)] if r.where else []
        r.where = parts[0] if parts else r.where
        if len(parts) == 2:
            r.other = parts[1]
        r.rest = r.reason
        m = re.search(r"(?:\bB\s*(?:says\s*)?:?|\bsays)\s*[`«\"](.+?)[`»\"]", r.reason)
        if m:
            r.other_q = m.group(1)
            r.rest = (r.reason[:m.start()] + r.reason[m.end():]).strip(" —–-")
            if not r.other:   # legacy: "<file>:<n> says `…`" inside why
                lm = re.search(r"([\w./\\-]+:\d+(?:-\d+)?)\s+says", r.reason)
                r.other = lm.group(1) if lm else ""
                if lm:
                    r.rest = re.sub(r"[\w./\\-]+:\d+(?:-\d+)?\s*", "", r.rest, count=1).strip(" —–-")
        rows.append(r)
    return rows


@dataclass
class Report:
    title: str
    exec_line: str
    corpus: int | None
    top: list[str]
    sections: list[dict]    # {key,title,rows,extra}
    pre_md: str             # preamble text that is neither title, exec line nor a top-action bullet
    tail: list[tuple[str, str]]   # sections rendered generically (Appendix …)
    has_where: bool
    has_b: bool


def corpus_bytes(text: str) -> int | None:
    m = re.search(r"corpus\s+([\d,]+)\s*B\b", text, re.I)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"corpus\s+([\d.]+)\s*(KB|MB)", text, re.I)
    if m:
        return int(float(m.group(1)) * (1024 if m.group(2).upper() == "KB" else 1024 ** 2))
    return None


def parse(md: str, title: str = "report") -> Report | None:
    """Funnel structure or None (the caller falls back to the generic view)."""
    md = md.lstrip("\ufeff")   # Windows editors / PowerShell prepend a BOM
    chunks, cur, fence = [], [], False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            chunks.append(cur)
            cur = []
        cur.append(line)
    chunks.append(cur)
    pre, secs = chunks[0], chunks[1:]
    sections, tail = [], []
    any_rows = has_where = has_b = False
    for ch in secs:
        name = ch[0][3:].strip()
        key = SEC_KEY.get(name[:1])
        table, heads, extra = [], None, []
        for s in ch[1:]:
            if s.strip().startswith("|"):
                cells = split_row(s)
                if set("".join(cells)) <= set("-: "):
                    continue
                if heads is None:
                    heads = cells
                else:
                    table.append(cells)
            else:
                extra.append(s)
        rows = parse_rows(heads, table, key) if key and heads else []
        if rows and sum(r.verb in VERBS for r in rows) * 2 >= len(rows):
            has_where |= any(r.where for r in rows)
            has_b |= any(r.b is not None for r in rows)
            any_rows |= bool(rows)
            sections.append({"key": key, "title": name, "rows": rows, "extra": "\n".join(extra).strip()})
        else:
            tail.append((name, "\n".join(ch)))
    if not any_rows:
        return None
    exec_line, top, title_line, other = "", [], "", []
    for line in pre:
        s = line.strip()
        if s.startswith("# ") and not title_line:
            title_line = s[2:]
        elif not exec_line and (" act now · " in s or re.match(r"^🔴.*shed", s)):
            exec_line = s
        else:
            if s.startswith(("- ", "* ")):
                top.append(s[2:])
            other.append(line)
    corpus = corpus_bytes("\n".join(pre) + "\n" + "\n".join(t[1] for t in tail))
    return Report(title_line or "HiViz audit report", exec_line, corpus, top, sections, "\n".join(other).strip(), tail, has_where, has_b)


def all_rows(rep: Report) -> list[Row]:
    return [r for s in rep.sections for r in s["rows"]]


_DRIVE = re.compile(r"^[A-Za-z]:/")


def posix(p: str) -> str:
    """Windows paths (C:\\x\\y, C:/x/y, \\\\host\\share) -> forward slashes, for display and prefix math."""
    return p.replace("\\", "/") if "\\" in p and ("/" not in p or re.match(r"^(?:[A-Za-z]:|\\\\)", p)) else p


def _fold(p: str) -> str:
    return p.lower() if _DRIVE.match(p) else p   # drive paths are case-insensitive


def common_dir(rows: list[Row]) -> str:
    dirs = [posix(split_loc(p)[0]).rpartition("/")[0] for r in rows for p in (r.where, r.other)
            if p and "/" in posix(split_loc(p)[0])]
    if not dirs:
        return ""
    fold = (lambda x: x.lower()) if all(_DRIVE.match(d + "/") for d in dirs) else (lambda x: x)
    common = []
    for segs in zip(*(d.split("/") for d in dirs), strict=False):   # stop at the shortest path
        if len({fold(x) for x in segs}) != 1:
            break
        common.append(segs[0])
    base = "/".join(common)
    return "" if base in ("", "/") or re.fullmatch(r"[A-Za-z]:", base) else base


def short(loc: str, base: str) -> str:
    path, ln = split_loc(loc)
    path = posix(path)
    if base and _fold(path).startswith(_fold(base) + "/"):
        path = path[len(base) + 1:]
    return path + (f":{ln}" if ln else "")


def tail(s: str, n: int) -> str:
    """Keep the end of a path (file name and line matter most)."""
    return s if len(s) <= n else "…" + s[-(n - 1):]


def tail_end(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def fmt_b(n: int | None) -> str:
    if n is None:
        return ""
    return f"{n / 1024:.1f} KB" if n >= 1024 else f"{n} B"


# ------------------------------------------------------------------ HTML
def inline(s: str) -> str:
    s = H.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


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
                  ("verb" if c.strip() in VERBS else "")
            cells.append(f'<td class="{cls}">{inline(c)}</td>')
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def render_generic(md: str) -> str:
    """Plain markdown -> HTML (headers, tables, code, quotes, bullets). Also the fallback view."""
    out, in_code, table, open_details, in_ul = [], False, [], False, False

    def flush_table():
        nonlocal table
        if table:
            out.append(table_html(table))
            table = []

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for line in md.splitlines():
        if line.strip().startswith("```"):
            close_ul()
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(H.escape(line))
            continue
        s = line.strip()
        if s.startswith("|"):
            cells = split_row(s)
            if set("".join(cells)) <= set("-: "):
                continue
            table.append(cells)
            continue
        flush_table()
        if not s:
            continue
        if s.startswith(("- ", "* ")):
            if not in_ul:
                out.append('<ul class="top">')
                in_ul = True
            out.append(f"<li>{inline(s[2:])}</li>")
            continue
        close_ul()
        if s.startswith("## "):
            name = s[3:]
            first = "Appendix" if name.startswith("Appendix") else name[:1]
            cls = {"🔴": "act", "🟡": "h2y", "⚪": "h2k", "Appendix": "apx"}.get(first, "")
            if open_details:
                out.append("</div></details>")
                open_details = False
            if first in ("⚪", "Appendix"):
                out.append(f'<details><summary><h2 class="{cls}" style="display:inline">{H.escape(name)}</h2></summary><div>')
                open_details = True
            else:
                out.append(f'<h2 class="{cls}">{H.escape(name)}</h2>')
        elif s.startswith("# "):
            out.append(f"<h1>{H.escape(s[2:])}</h1>")
        elif re.match(r"^🔴.*shed", s) or " act now · " in s:
            out.append(f'<div class="exec">{colorize_exec(s)}</div>')
        elif s.startswith("> "):
            out.append(f"<blockquote>{inline(s[2:])}</blockquote>")
        else:
            out.append(f"<p>{inline(s)}</p>")
    flush_table()
    close_ul()
    if in_code:
        out.append("</pre>")
    if open_details:
        out.append("</div></details>")
    return "".join(out)


def row_html(r: Row, base: str, need: bool, maxb: int) -> str:
    sym = hvfmt.STATUS.get(r.verb, ("•", "*", "gray"))[0]
    cls = f"v-{r.verb}" if r.verb in VERBS else ""
    where = short(r.where, base) if r.where else ""
    meta = [f'<span class="id">{H.escape(r.id)}</span>',
            f'<span class="verb">{sym} {H.escape(r.verb)}</span>']
    if r.cat:
        meta.append(f'<span class="cat">{H.escape(r.cat)}</span>')
    if where:
        meta.append(f'<span class="where" title="{H.escape(r.where, quote=True)}">{H.escape(where)}</span>')
    eff = ""
    if r.b is not None:
        w = 0 if maxb <= 0 else max(2 if r.b else 0, round(100 * r.b / maxb))
        eff = f'<div class="eff"><span class="bar"><i style="width:{w}%"></i></span>{fmt_b(r.b)}</div>'
    q = f'<pre class="q">{H.escape(unwrap(r.line))}</pre>'
    why = ""
    if r.conflict and r.other:
        why = ('<div class="conf"><div class="side"><div class="w">A · {a}</div><div class="t">{aq}</div></div>'
               '<div class="sw">⇄</div><div class="side"><div class="w">B · {b}</div><div class="t">{bq}</div></div></div>'
               ).format(a=H.escape(where or "?"), aq=H.escape(unwrap(r.line)),
                        b=H.escape(short(r.other, base)), bq=H.escape(r.other_q or "(see the reason below)"))
        q = ""
    ev = f'<span class="ev">{"measured" if r.ev == "fact" else "judgment"}</span>' if r.ev else ""
    reason = r.rest if (r.conflict and r.other) else r.reason   # side B is already shown in the card
    why += f'<div class="why">{ev}{inline(reason)}</div>'
    dec = ""
    if need:
        dec = ('<div class="dec"><span class="seg">'
               '<button data-v="yes" aria-pressed="false">yes</button><button data-v="no" aria-pressed="false">no</button>'
               '<button data-v="keep" aria-pressed="false">keep</button><button data-v="cond" aria-pressed="false">as-condition</button>'
               '</span><input class="note" placeholder="condition…" aria-label="condition"></div>')
    return (f'<div class="row {cls}" data-id="{H.escape(r.id, quote=True)}" data-sec="{r.sec}"'
            f'{" data-need" if need else ""}><div class="meta">{"".join(meta)}</div>{eff}'
            f'<div class="body">{q}{why}</div>{dec}</div>')


def batch_html(srows: list[Row], key: str, has_b: bool) -> str:
    groups: dict[tuple[str, str], list[Row]] = {}
    for r in srows:
        if r.cat and r.verb in ("delete", "rewrite", "merge", "disable") and not r.conflict:
            groups.setdefault((r.cat, r.verb), []).append(r)
    chips = []
    for (cat, verb), g in sorted(groups.items(), key=lambda kv: -sum(x.b or 0 for x in kv[1])):
        if len(g) < 2:
            continue
        size = f" · {fmt_b(sum(x.b or 0 for x in g))}" if has_b else ""
        chips.append(f'<span class="chip" data-sec="{key}" data-cat="{H.escape(cat, quote=True)}" data-verb="{verb}">'
                     f'{hvfmt.STATUS[verb][0]} {verb} · <b>{H.escape(cat)}</b> · {len(g)} rows{size}'
                     f'<button data-batch="1">yes to <span class="left">{len(g)}</span> undecided</button></span>')
    return '<div class="batch"><span class="lbl">batch</span>' + "".join(chips) + "</div>" if chips else ""


def render(md: str, title: str) -> str:
    rep = parse(md, title)
    if rep is None:
        return ("<!doctype html><html><head><meta charset='utf-8'>"
                f"<title>{H.escape(title)}</title><style>{STYLE}</style></head>"
                f"<body><div class='wrap'>{render_generic(md)}"
                "<div class='foot'>generated view — regenerate, never hand-edit · hiviz</div>"
                "</div></body></html>")
    rows = all_rows(rep)
    base = common_dir(rows)
    maxb = max([r.b or 0 for r in rows] + [0])
    cols = ["id"] + (["where"] if rep.has_where else []) + ["line", "why"] + (["b"] if rep.has_b else []) + ["verb"]
    key = hashlib.sha1("|".join(r.id + r.line for r in rows).encode("utf-8")).hexdigest()[:12]
    data = {"key": key, "corpus": rep.corpus or 0, "cols": cols, "labels": LABELS,
            "sections": [{"key": s["key"], "title": s["title"]} for s in rep.sections],
            "rows": [{"id": r.id, "sec": r.sec,
                      "where": r.where + (f" ⇄ {r.other}" if r.other else ""), "line": r.line, "why": r.why,
                      "b": r.b, "verb": r.verb, "cat": r.cat, "i": r.i} for r in rows]}
    parts = []
    for s in rep.sections:
        srows = sorted(s["rows"], key=lambda r: -(r.b or 0))
        need = s["key"] != "safe"
        cls = {"act": "act", "call": "h2y", "safe": "h2k"}[s["key"]]
        batch = batch_html(srows, s["key"], rep.has_b) if need else ""
        inner = f'{batch}<div class="rows">{"".join(row_html(r, base, need, maxb) for r in srows)}</div>'
        inner += render_generic(s["extra"]) if s["extra"] else ""
        count = f' <span style="font-weight:400;color:#8a93a0">— {len(srows)}{"" if need else " lines, invariants · folded"}</span>'
        if need:
            parts.append(f'<section class="sec" data-need><h2 class="{cls}">{H.escape(s["title"])}{count}</h2>{inner}</section>')
        else:
            parts.append(f'<details class="safe"><summary><h2 class="{cls}" style="display:inline">{H.escape(s["title"])}{count}</h2>'
                         f'</summary><section class="sec">{inner}</section></details>')
    shed_span = "<span id=p-shed></span>" if rep.has_b and rep.corpus else "<span id=p-shed hidden></span>"
    sort_ctl = ('<div class="toolbar"><span class="lbl">sort rows by</span><span class="sortgrp">'
                '<button data-s="effect" aria-pressed="true">effect</button><button data-s="file" aria-pressed="false">file</button>'
                '<button data-s="id" aria-pressed="false">id</button></span></div>'
                if rep.has_b or rep.has_where else "")
    bar = ('<div class="top-bar"><div class="in">'
           f'<div class="exec">{colorize_exec(rep.exec_line) if rep.exec_line else H.escape(rep.title)}</div>'
           '<div class="stats"><span class="prog"><span class="bar"><i id="p-bar"></i></span><span id="p-txt"></span></span>'
           f'<span id="p-split"></span>{shed_span}<span class="ctl">'
           '<button id="b-cp">Copy decisions.md</button><button id="b-dl" class="go">Export decisions.md</button>'
           '<button id="b-rs" title="clear all decisions">Reset</button></span></div></div></div>')
    script_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "\\u003c!--")
    pre = render_generic(rep.pre_md) if rep.pre_md else ""
    tail = "".join(render_generic(m) for _, m in rep.tail)
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{H.escape(rep.title)}</title><style>{STYLE}</style></head><body>"
            f"{bar}<div class='wrap'><h1>{H.escape(rep.title)}</h1>"
            f"{pre}{sort_ctl}{''.join(parts)}{tail}"
            "<details><summary>Preview decisions.md</summary><pre id='prev'></pre></details>"
            "<div class='hint'>↑ ↓ move · y yes · n no · k keep · c as-condition · decisions stay in this browser only; "
            "nothing is pre-decided — empty means leave the line untouched</div>"
            "<div class='foot'>generated view — regenerate, never hand-edit · hiviz</div></div>"
            f"<div id='toast'></div><script type='application/json' id='hv-data'>{script_json}</script>"
            f"<script>{SCRIPT}</script></body></html>")


# ------------------------------------------------------------------ terminal
def _plain(s: str) -> str:
    return re.sub(r"[`*]", "", s)


def summary_md(md: str, md_path: str = "", html_path: str = "", decisions_path: str = "", limit: int = 8) -> str:
    """Plain markdown summary — what an agent or a CI log gets: no box drawing, no color."""
    rep = parse(md)
    if rep is None:
        return f"audit report {md_path}: not in the funnel format"
    base = common_dir(all_rows(rep))
    out = [f"# {rep.title}", "", rep.exec_line] if rep.exec_line else [f"# {rep.title}"]
    for s in rep.sections:
        if s["key"] == "safe" or not s["rows"]:
            continue
        rs = sorted(s["rows"], key=lambda r: -(r.b or 0))
        out += ["", f"## {s['title']} ({len(rs)}, by effect)", "", "| id | verb | where | category | size | line |", "|---|---|---|---|---:|---|"]
        for r in rs[:limit]:
            line = " ".join(unwrap(r.line).split()).replace("|", "\\|")
            out.append(f"| {r.id} | {r.verb} | {short(r.where, base) if r.where else ''} | {r.cat} | {fmt_b(r.b)} | {tail_end(line, 60)} |")
        if len(rs) > limit:
            out.append(f"\n… and {len(rs) - limit} more — all rows in the HTML view")
    safe = next((len(s["rows"]) for s in rep.sections if s["key"] == "safe"), 0)
    if safe:
        out.append(f"\n{safe} lines kept safe — invariants, nothing to decide")
    out += [f"\n{label}: {path}" for label, path in (("report", md_path), ("html", html_path), ("decisions", decisions_path)) if path]
    return "\n".join(out)


def summary_json(md: str, md_path: str = "", html_path: str = "", decisions_path: str = "") -> str:
    """The whole report as one JSON document (every row, every section) for scripts and agents."""
    rep = parse(md)
    if rep is None:
        return hvfmt.dumps({"funnel": False, "report": md_path})
    return hvfmt.dumps({
        "funnel": True, "title": rep.title, "executive": rep.exec_line, "corpus_bytes": rep.corpus,
        "paths": {"report": md_path, "html": html_path, "decisions": decisions_path},
        "sections": [{"key": s["key"], "title": s["title"], "rows": [
            {"id": r.id, "verb": r.verb, "where": r.where, "other": r.other, "line": unwrap(r.line),
             "category": r.cat, "reason": r.reason, "bytes": r.b} for r in s["rows"]]} for s in rep.sections]})


def terminal(md: str, md_path: str = "", html_path: str = "", decisions_path: str = "", limit: int = 8) -> str:
    """Human summary for the console: counts, top actions, the rows to decide (by effect), paths."""
    if hvfmt.is_json():
        return summary_json(md, md_path, html_path, decisions_path)
    if not hvfmt.is_pretty():
        return summary_md(md, md_path, html_path, decisions_path, limit)
    rep = parse(md)
    out: list[str] = []
    P = out.append
    if rep is None:
        P(hvfmt.heading("audit report", md_path))
        P(hvfmt.style("  not in the funnel format — open the markdown directly", "gray"))
        return "\n".join(out)
    rows = all_rows(rep)
    base = common_dir(rows)
    counts = {s["key"]: len(s["rows"]) for s in rep.sections}
    P(hvfmt.heading("audit report", rep.title))
    dot = "●" if hvfmt._STATE["unicode"] else "*"
    shed = re.search(r"corpus\s+[\d.,]+\s*\w+\s*→\s*shed\s*[−-]?\s*([\d.]+%)", rep.exec_line)
    corpus = re.search(r"(corpus\s+[\d.,]+\s*\w+)", rep.exec_line)
    P("  " + "   ".join([f"{hvfmt.style(dot, 'red')} {counts.get('act', 0)} act now",
                         f"{hvfmt.style(dot, 'yellow')} {counts.get('call', 0)} your call",
                         f"{hvfmt.style(dot, 'gray')} {counts.get('safe', 0)} kept safe"])
      + (hvfmt.style(f"   {corpus.group(1)} → shed −{shed.group(1)}", "gray") if corpus and shed else ""))
    room = hvfmt.term_cols() - 6
    for t in rep.top[:3]:
        t = _plain(t)
        P("  " + hvfmt.style("›", "cyan") + " " + (t if len(t) <= room else t[:room - 1] + "…"))
    for s in rep.sections:
        if s["key"] == "safe" or not s["rows"]:
            continue
        rs = sorted(s["rows"], key=lambda r: -(r.b or 0))
        P(hvfmt.heading(re.sub(r"^[🔴🟡⚪]\s*", "", s["title"]), f"{len(rs)} · by effect"))
        cap = max(20, min(64, hvfmt.term_cols() - 72))   # 72 = other columns + borders; keeps one row per entry
        body = [[r.id, r.verb if r.verb in VERBS else "", tail(short(r.where, base), 22) if r.where else "",
                 tail_end(" ".join(unwrap(r.line).split()), cap), r.cat or "", fmt_b(r.b)] for r in rs[:limit]]
        P(hvfmt.table(["id", "→", "where", "line", "category", "size"], body, status_col=1,
                      align=["l", "l", "l", "l", "l", "r"], dim_cols=(2, 4)))
        if len(rs) > limit:
            P(hvfmt.style(f"  … and {len(rs) - limit} more — all rows in the HTML view", "gray"))
        for r in rs:
            if r.conflict and r.other:
                sw = "⇄" if hvfmt._STATE["unicode"] else "<>"
                wa, wb = tail(short(r.where, base), 30), tail(short(r.other, base), 30)
                w = max(len(wa), len(wb))
                room = max(20, hvfmt.term_cols() - w - 14)
                def q(t: str, room: int = room) -> str:
                    return hvfmt.style("“" + (t if len(t) <= room else t[:room - 1] + "…") + "”", "dim") if t else ""
                P(f"  {hvfmt.style(sw, 'red')} {hvfmt.style(r.id, 'bold')}  {wa.ljust(w)}  {q(unwrap(r.line))}")
                P(f"       {wb.ljust(w)}  {q(r.other_q)}")
    if counts.get("safe"):
        P("\n  " + hvfmt.style(f"{counts['safe']} lines kept safe — invariants, nothing to decide (listed in the HTML view)", "gray"))
    for label, path in (("report ", md_path), ("html   ", html_path), ("decide ", decisions_path)):
        if path:
            P("  " + hvfmt.style(label, "gray") + " " + path)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz report renderer")
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", default=None, help="write the HTML view here")
    ap.add_argument("--summary", action="store_true", help="print the terminal summary")
    hvfmt.add_format_arg(ap)
    a = ap.parse_args()
    hvfmt.configure(a.format)
    src = Path(a.md)
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    if not a.out and not a.summary:
        print("nothing to do: pass --out <file.html> and/or --summary", file=sys.stderr)
        return 2
    md = src.read_text(encoding="utf-8-sig")
    if a.out:
        html = render(md, src.stem)
        Path(a.out).write_text(html, encoding="utf-8")
        print(f"html view: {a.out} ({len(html):,} bytes)", file=sys.stderr if hvfmt.is_json() else sys.stdout)
    if a.summary:
        print(terminal(md, str(src), a.out or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
