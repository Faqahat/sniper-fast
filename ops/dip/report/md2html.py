#!/usr/bin/env python3
# Combine the run reports (ops/dip/reports/runs/*.md) into ONE phone-friendly HTML file with a table of contents:
# ops/dip/reports/runs/RUN_REPORTS.html. Minimal Markdown subset (what make_run_report.py writes): headings, tables,
# bullet lists, blockquotes, bold / italic / code / links. No external libraries.
import os, re, html, glob, datetime as dt

D = "/home/moiz/sniper/ops/dip/reports/runs"

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\(([A-Z]{3}_run\d+)\.md\)", r'<a href="#\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<i>\1</i>", s)
    return s

def convert(md, anchor):
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-|\s:]+\|$", lines[i + 1]):
            head = [c.strip() for c in l.strip().strip("|").split("|")]
            i += 2; rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{inline(h)}</th>" for h in head) + "</tr></thead><tbody>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")
            continue
        if l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "): items.append(lines[i][2:]); i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"); continue
        m = re.match(r"^(#{1,3}) (.*)$", l)
        if m:
            n = len(m.group(1)); txt = m.group(2)
            out.append(f'<h{n + 1}{" id=" + chr(34) + anchor + chr(34) if n == 1 else ""}>{inline(txt)}</h{n + 1}>'); i += 1; continue
        if l.startswith("> "): out.append(f"<blockquote>{inline(l[2:])}</blockquote>"); i += 1; continue
        if l.strip(): out.append(f"<p>{inline(l)}</p>")
        i += 1
    return "\n".join(out)

def main():
    idx = open(f"{D}/INDEX.md").read()
    files = sorted(glob.glob(f"{D}/*_run*.md"), key=lambda f: (os.path.basename(f)[:3] != "FRA", f))
    order = []
    for m in re.finditer(r"\(([A-Z]{3}_run\d+)\.md\)", idx): order.append(m.group(1))
    names = order or [os.path.basename(f)[:-3] for f in files]
    body = [convert(idx.replace("# Dip bot runs — index", "# Dip bot run reports"), "index")]
    for nm in names:
        p = f"{D}/{nm}.md"
        if os.path.exists(p): body.append('<hr><p class="top"><a href="#index">↑ index</a></p>' + convert(open(p).read(), nm))
    css = """
:root{--bg:#ffffff;--fg:#1d1d1f;--muted:#6e6e73;--line:#d9d9de;--head:#f3f3f6;--link:#0a58ca;--code:#f0f0f3;--quote:#f6f8fa}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141416;--fg:#e8e8ea;--muted:#a1a1a6;--line:#38383d;--head:#1f1f23;--link:#6ea8fe;--code:#26262b;--quote:#1c1f24}}
:root[data-theme="dark"]{--bg:#141416;--fg:#e8e8ea;--muted:#a1a1a6;--line:#38383d;--head:#1f1f23;--link:#6ea8fe;--code:#26262b;--quote:#1c1f24}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;padding:0 16px 48px;max-width:1100px}
h2{font-size:1.45em;margin:1.4em 0 .4em} h3{font-size:1.15em;margin:1.3em 0 .4em;border-bottom:1px solid var(--line);padding-bottom:.2em}
a{color:var(--link);text-decoration:none} code{background:var(--code);padding:0 .25em;border-radius:4px;font-size:.92em}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:.5em 0}
table{border-collapse:collapse;font-size:.88em;min-width:60%} th,td{border:1px solid var(--line);padding:4px 7px;text-align:left;vertical-align:top}
th{background:var(--head)} blockquote{margin:.6em 0;padding:.5em .8em;background:var(--quote);border-left:3px solid var(--link)}
ul{padding-left:1.2em} hr{border:0;border-top:2px solid var(--line);margin:2em 0 0} .top{font-size:.85em;margin:.4em 0 0}
"""
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5))).strftime("%m-%d %H:%M")
    html_ = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dip Run Reports</title><style>{css}</style></head><body>
{"".join(body)}
<p style="color:var(--muted);font-size:.85em">Generated {now} PKT by ops/dip/report/make_run_report.py + md2html.py</p></body></html>"""
    open(f"{D}/RUN_REPORTS.html", "w").write(html_)
    print(f"wrote {D}/RUN_REPORTS.html ({len(html_) // 1024} KB, {len(names)} runs)")

if __name__ == "__main__":
    main()
