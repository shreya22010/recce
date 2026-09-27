"""Rendering a package to a PDF you can take into the exam hall.

Printed through headless Chrome rather than a PDF library, because the package
is already laid out as HTML and a second layout engine means a second set of
bugs. Chrome is on every machine this runs on.

The print stylesheet is not the screen one. On paper there is no hover, no
collapsing and no dark mode, and a question that breaks across a page boundary
is genuinely annoying, so blocks are kept whole.
"""
import html
import json
import os
import shutil
import subprocess
import tempfile

CHROME = next((p for p in [
    os.environ.get("CHROME_BIN", ""),
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
] if p and os.path.exists(p)), None)

CSS = """
@page { size: A4; margin: 15mm 14mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif;
       color: #16255C; margin: 0; }
h1 { font-size: 22pt; margin: 0 0 2mm; letter-spacing: -.02em; }
.lede { color: #5C6788; font-size: 10pt; margin: 0 0 8mm; }
h2 { font-size: 13pt; margin: 9mm 0 3mm; padding-bottom: 2mm;
     border-bottom: 2px solid #F7C948; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 6mm 0 2mm; color: #24376F; page-break-after: avoid; }
table { width: 100%; border-collapse: collapse; margin-bottom: 4mm; }
td, th { border: .5pt solid #E8E1D1; padding: 2mm 3mm; text-align: left;
         font-size: 9.5pt; vertical-align: top; }
th { background: #FBF7EC; font-weight: 600; }
.box { border: .5pt solid #E8E1D1; border-radius: 2mm; padding: 3mm 4mm;
       margin-bottom: 3mm; page-break-inside: avoid; }
.f { background: #FEF3D0; border-color: #F7C948; }
.f b { font-size: 8.5pt; text-transform: uppercase; letter-spacing: .06em; color: #8A6A10; }
.q { font-weight: 600; margin-bottom: 1.5mm; }
ol, ul { margin: 0 0 2mm; padding-left: 5mm; }
li { font-size: 9.5pt; line-height: 1.55; }
.ans { background: #E2F3E9; border-radius: 1.5mm; padding: 1.5mm 3mm;
       font-size: 9.5pt; margin-top: 1.5mm; }
.ans b { color: #1C7A4E; }
pre { background: #FBF7EC; border: .5pt solid #E8E1D1; border-radius: 1.5mm;
      padding: 2.5mm 3mm; overflow: hidden; white-space: pre-wrap;
      font: 8.5pt/1.45 "SF Mono", Menlo, monospace; margin: 2mm 0; }
.tag { font-size: 7.5pt; font-weight: 700; padding: .4mm 1.5mm; border-radius: 1mm;
       text-transform: uppercase; letter-spacing: .04em; }
.rep { background: #1C7A4E; color: #fff; }
.pre { background: #EAF4F8; color: #5C6788; }
.src { font-size: 8pt; color: #5C6788; margin-top: 1.5mm; }
.src a { color: #2F5FD8; text-decoration: none; }
.foot { margin-top: 10mm; padding-top: 3mm; border-top: .5pt solid #E8E1D1;
        font-size: 8pt; color: #9AA2B8; }
"""


def _e(s):
    return html.escape(str(s or ""))


def _qa(q, company):
    src = ""
    if q.get("tag") == "reported" and q.get("drives"):
        bits = [f"{d['campus']}, {d['date']}" for d in q["drives"][:3]]
        src = (f"<div class='src'><b>Reported</b> by {q.get('students', 0)} "
               f"student(s) &middot; {_e('; '.join(bits))}</div>")
    elif q.get("verify"):
        links = " &middot; ".join(
            f"<a href='{_e(v['url'])}'>{_e(v['site'])}</a>" for v in q["verify"][:3])
        src = f"<div class='src'>Not confirmed for {_e(company)}. Check: {links}</div>"

    extra = ""
    if q.get("practice_url"):
        extra += (f"<div class='src'>Practise: "
                  f"<a href='{_e(q['practice_url'])}'>{_e(q['practice_url'])}</a></div>")
    if q.get("complexity"):
        extra += f"<div class='src'>{_e(q['complexity'])}</div>"

    return f"""<div class="box">
      <div class="q">{_e(q.get('q') or q.get('text'))}
        <span class="tag {'rep' if q.get('tag') == 'reported' else 'pre'}">
        {'reported' if q.get('tag') == 'reported' else 'predicted'}</span></div>
      {"<ul>" + "".join(f"<li>{_e(o)}</li>" for o in q["options"]) + "</ul>" if q.get("options") else ""}
      {f"<pre>{_e(q['code'])}</pre>" if q.get("code") else ""}
      {f"<div>{_e(q['approach'])}</div>" if q.get("approach") else ""}
      {"<ol>" + "".join(f"<li>{_e(s)}</li>" for s in q["steps"]) + "</ol>" if q.get("steps") else ""}
      {f"<div class='ans'><b>Answer:</b> {_e(q['answer'])}</div>" if q.get("answer") else ""}
      {f"<div class='src'>{_e(q['why'])}</div>" if q.get("why") else ""}
      {extra}{src}</div>"""


def _section(sec, company):
    c = sec.get("content") or {}
    out = [f"<h2>{_e(sec['title'])}</h2>"]

    if sec["section"] == "overview":
        rows = [("Role", c.get("role")),
                ("Process", " → ".join(c.get("process") or [])),
                ("Eligibility", " · ".join(c.get("eligibility") or [])),
                ("Keep ready", ", ".join(c.get("keep_ready") or []))]
        out.append("<table>" + "".join(
            f"<tr><th style='width:28mm'>{_e(k)}</th><td>{_e(v)}</td></tr>"
            for k, v in rows if v) + "</table>")
        for f in c.get("formats") or []:
            out.append(f"<div class='box'><div class='q'>{_e(f.get('name'))}</div>"
                       + "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in f.get("sections") or [])
                       + f"</ul><div class='src'>{_e(f.get('seen_in'))}</div></div>")
        if c.get("what_decides"):
            out.append("<h3>What decides selection</h3><ul>"
                       + "".join(f"<li>{_e(x)}</li>" for x in c["what_decides"]) + "</ul>")

    elif sec["section"] == "plan":
        out.append("<table><tr><th>Day</th><th>Focus</th><th>Hours</th></tr>" + "".join(
            f"<tr><td>{_e(d.get('day'))}</td><td>{_e(d.get('focus'))}</td>"
            f"<td>{_e(d.get('hours'))}</td></tr>" for d in c.get("days") or []) + "</table>")
        for label, key in (("Test-day checklist", "checklist"),
                           ("Mistakes people make", "mistakes")):
            if c.get(key):
                out.append(f"<h3>{label}</h3><ul>"
                           + "".join(f"<li>{_e(x)}</li>" for x in c[key]) + "</ul>")

    elif sec["section"] == "reviews":
        out.append("<div class='box'><b>Where this comes from.</b> The pay ranges and opinions "
                   "below are what employees and candidates commonly report, summarised. They "
                   "are not figures taken from any review site and nobody has verified them. "
                   "Check AmbitionBox, Glassdoor or Levels.fyi before relying on a number.</div>")
        if c.get("ctc"):
            out.append("<table><tr><th>Role</th><th>Fresher CTC</th><th>Bond</th><th>Note</th></tr>"
                       + "".join(f"<tr><td>{_e(x.get('role'))}</td><td>{_e(x.get('fresher_ctc'))}</td>"
                                 f"<td>{_e(x.get('bond'))}</td><td>{_e(x.get('note'))}</td></tr>"
                                 for x in c["ctc"]) + "</table>")
        for r in c.get("reviews") or []:
            out.append(f"<div class='box'><div class='q'>{_e(r.get('topic'))} "
                       f"<span class='tag pre'>{_e(r.get('sentiment'))}</span></div>"
                       f"<div>{_e(r.get('says'))}</div>"
                       f"<div class='src'>What employees report, not verified</div></div>")
        if c.get("watch_out"):
            out.append("<h3>What candidates wish they had known</h3><ul>"
                       + "".join(f"<li>{_e(x)}</li>" for x in c["watch_out"]) + "</ul>")

    elif sec["section"] in ("coding", "hr"):
        for q in (c.get("problems") or []) + (c.get("questions") or []):
            out.append(_qa(q, company))
        for label, key in (("What they ask about your project", "project_questions"),
                           ("Know this about them", "about_company")):
            if c.get(key):
                out.append(f"<h3>{label}</h3><ul>"
                           + "".join(f"<li>{_e(x)}</li>" for x in c[key]) + "</ul>")
    else:
        if c.get("advice"):
            out.append("<div class='box f'><b>How this round is scored</b><ul>"
                       + "".join(f"<li>{_e(x)}</li>" for x in c["advice"]) + "</ul></div>")
        for t in c.get("topics") or []:
            out.append(f"<h3>{_e(t.get('name'))}</h3>")
            if t.get("formulas"):
                out.append("<div class='box f'><b>Formulas</b><ul>"
                           + "".join(f"<li>{_e(x)}</li>" for x in t["formulas"]) + "</ul></div>")
            for q in t.get("questions") or []:
                out.append(_qa(q, company))
    return "\n".join(out)


def build_html(pkg, sections=None):
    company = pkg["company"]
    secs = [s for s in pkg["sections"] if s.get("content")
            and (not sections or s["section"] in sections)
            and s.get("applies", True)]

    drives = pkg.get("drives") or []
    drive_tbl = ""
    if drives:
        drive_tbl = ("<h2>Reported drives</h2><table>"
                     "<tr><th>Date</th><th>College</th><th>Role</th><th>Rounds</th>"
                     "<th>Reported by</th></tr>" + "".join(
            f"<tr><td>{_e(d['date'])}</td><td>{_e(d['campus'])}</td>"
            f"<td>{_e(d['role'])}</td><td>{_e(' → '.join(d['rounds']))}</td>"
            f"<td>{d['students']}</td></tr>" for d in drives) + "</table>")
    else:
        drive_tbl = ("<div class='box'><b>No candidate reports yet.</b> Nothing in this "
                     "package is confirmed for this company; every item is marked predicted "
                     "and carries a link to check it.</div>")

    from datetime import date
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_e(company)} prep package</title><style>{CSS}</style></head><body>
<h1>{_e(company)}</h1>
<p class="lede">Campus placement preparation package &middot; compiled {date.today().isoformat()}
 &middot; {len(secs)} section(s)</p>
{drive_tbl}
{"".join(_section(s, company) for s in secs)}
<div class="foot">Items marked <b>reported</b> come from students who sat the drive, with the
date and college shown. Items marked <b>predicted</b> are standard material for this kind of
drive and are not confirmed for {_e(company)} &mdash; each carries links to check it.</div>
</body></html>"""


def to_pdf(html_text, out_path):
    """Chrome when it is there, a bundled renderer when it is not.

    Chrome is on every laptop and on almost no host. Rather than make the PDF a
    feature that silently stops existing in production, fall back to WeasyPrint,
    which is a pip install and renders the same HTML. The Chrome path stays
    first because its output is better.
    """
    if not CHROME:
        return _weasy(html_text, out_path)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "doc.html")
        with open(src, "w") as f:
            f.write(html_text)
        try:
            # --no-sandbox is required in a container, where there is no user
            # namespace for Chromium to drop into.
            subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                            "--disable-dev-shm-usage", "--no-pdf-header-footer",
                            f"--print-to-pdf={out_path}", f"file://{src}"],
                           check=True, capture_output=True, timeout=120)
        except Exception:
            return _weasy(html_text, out_path)
    return out_path


def _weasy(html_text, out_path):
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError(
            "No PDF renderer available. Install weasyprint (pip install weasyprint) "
            "or run somewhere with Chrome.")
    HTML(string=html_text).write_pdf(out_path)
    return out_path
