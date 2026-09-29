"""Build docs/index.html: one self-contained page, data embedded as JSON."""
from __future__ import annotations

import json

from .state import active_jobs


def build(db: dict, quick_links: list, summary: dict, path):
    jobs = active_jobs(db)
    data = {
        "last_run": db.get("last_run", ""),
        "jobs": jobs,
        "links": quick_links,
        "summary": summary,
    }
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.replace("__DATA__", blob), encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>PJF</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mute:#6b6a66;--line:#e2e0da;--accent:#2f6fdf;
--new:#1f8a4c;--check:#b7791f;--star:#c2410c;--chip:#ecebe6}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--mute:#9a9892;
--line:#33322f;--accent:#7aa5f5;--new:#4cc281;--check:#e0a84a;--star:#f08a5d;--chip:#2a2a27}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:920px;margin:0 auto;padding:20px 16px 60px}
header h1{font-size:22px;margin:0}
header p{margin:4px 0 0;color:var(--mute);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 8px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;
padding:4px 11px;font:inherit;font-size:13px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.chip small{opacity:.65;margin-left:3px}
input[type=search]{flex:1 1 180px;min-width:0;border:1px solid var(--line);background:var(--card);color:var(--ink);
border-radius:8px;padding:5px 10px;font:inherit;font-size:14px}
details.links{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:12px 0}
details.links summary{cursor:pointer;font-size:14px;color:var(--mute)}
details.links ul{margin:8px 0 2px;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:6px 14px}
details.links li{font-size:14px}
details.links li span{color:var(--mute);font-size:12px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
ol{list-style:none;margin:0;padding:0}
li.job{background:var(--card);border:1px solid var(--line);border-left:3px solid transparent;border-radius:10px;
padding:10px 12px;margin:8px 0;display:flex;gap:10px;align-items:flex-start}
li.job.interesting{border-left-color:var(--star)}
li.job.applied{opacity:.6}
li.job.hide{opacity:.45}
.main{flex:1;min-width:0}
.t{font-weight:600;overflow-wrap:anywhere}
.meta{color:var(--mute);font-size:13px;margin-top:2px;overflow-wrap:anywhere}
.tag{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.02em;text-transform:uppercase;
border-radius:4px;padding:1px 5px;margin-right:5px;vertical-align:1px;background:var(--chip);color:var(--mute)}
.tag.new{background:var(--new);color:#fff}
.tag.check{background:transparent;color:var(--check);border:1px solid var(--check)}
.tag.m{background:transparent;color:var(--star);border:1px solid var(--star)}
.acts{display:flex;gap:4px;flex-shrink:0}
.acts button{border:1px solid var(--line);background:transparent;color:var(--mute);border-radius:6px;
width:30px;height:30px;font-size:15px;cursor:pointer;line-height:1}
.acts button[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.empty{color:var(--mute);text-align:center;padding:30px 0}
footer{color:var(--mute);font-size:12px;margin-top:24px}
</style>
</head>
<body>
<main>
<header>
  <h1>PJF</h1>
  <p id="status"></p>
</header>
<details class="links" id="links"><summary>Sites to check by hand</summary><ul></ul></details>
<div class="bar" id="fam"></div>
<div class="bar" id="view"><input type="search" id="q" placeholder="Search title, company, location"></div>
<ol id="list"></ol>
<footer id="foot"></footer>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const FAMILIES = [["all","All"],["data","Data"],["production","Production"],["operations","Operations"],
  ["localization","Localization"],["audio","Audio"]];
const VIEWS = [["open","Open"],["new","New"],["interesting","Interesting"],["applied","Applied"],["hide","Hidden"]];
let marks = {}, live = false, fam = "all", view = "open", q = "";
try { fam = localStorage.getItem("pjf.fam") || "all"; } catch (e) {}

const el = (tag, attrs, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) n.append(k);
  return n;
};
const safeUrl = u => /^https?:\/\//i.test(u || "") ? u : "#";
const day = ts => (ts || "").slice(0, 10);
const markOf = j => (marks[j.key] || {}).mark || "";
const isNew = j => j.first_seen === D.last_run;

function visible(j) {
  const m = markOf(j);
  if (view === "open" && m === "hide") return false;
  if (view === "new" && (!isNew(j) || m === "hide")) return false;
  if (["interesting", "applied", "hide"].includes(view) && m !== view) return false;
  if (q) {
    const hay = (j.title + " " + j.company + " " + j.location + " " + j.source).toLowerCase();
    if (!q.split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
}

function render() {
  const pool = D.jobs.filter(visible);
  const famBar = document.getElementById("fam");
  famBar.replaceChildren(...FAMILIES.map(([k, label]) => {
    const n = k === "all" ? pool.length : pool.filter(j => j.family === k).length;
    return el("button", {class: "chip", "aria-pressed": String(fam === k),
      onclick: () => { fam = k; try { localStorage.setItem("pjf.fam", k); } catch (e) {} render(); }},
      label, el("small", {}, String(n)));
  }));
  const viewBar = document.getElementById("view");
  viewBar.querySelectorAll(".chip").forEach(c => c.remove());
  const views = live ? VIEWS : VIEWS.slice(0, 2);
  const input = document.getElementById("q");
  for (const [k, label] of views) {
    viewBar.insertBefore(el("button", {class: "chip", "aria-pressed": String(view === k),
      onclick: () => { view = k; render(); }}, label), input);
  }

  const rows = pool.filter(j => fam === "all" || j.family === fam).sort((a, b) =>
    (isNew(b) - isNew(a)) || b.first_seen.localeCompare(a.first_seen) ||
    (b.posted || "").localeCompare(a.posted || "") || a.title.localeCompare(b.title));
  const list = document.getElementById("list");
  if (!rows.length) { list.replaceChildren(el("li", {class: "empty"}, "Nothing here.")); return; }
  list.replaceChildren(...rows.map(row));
}

function row(j) {
  const m = markOf(j);
  const tags = [];
  if (isNew(j)) tags.push(el("span", {class: "tag new"}, "new"));
  if (j.verdict === "check") tags.push(el("span", {class: "tag check", title: "Location or remote status unclear, read the ad"}, "check"));
  if (m === "applied") tags.push(el("span", {class: "tag m"}, "applied " + ((marks[j.key] || {}).date || "")));
  tags.push(el("span", {class: "tag"}, j.family));
  const meta = [j.company || "(company in ad)", j.location || "location not stated", j.source,
    "seen " + day(j.first_seen) + (j.posted ? ", posted " + j.posted : "")].join(" · ");
  const main = el("div", {class: "main"},
    el("div", {class: "t"}, ...tags, el("a", {href: safeUrl(j.url), target: "_blank", rel: "noopener"}, j.title)),
    el("div", {class: "meta"}, meta));
  const li = el("li", {class: "job " + m}, main);
  if (live) {
    const b = (kind, sym, label) => el("button", {"aria-pressed": String(m === kind), title: label,
      "aria-label": label, onclick: () => setMark(j.key, m === kind ? null : kind)}, sym);
    li.append(el("div", {class: "acts"}, b("interesting", "★", "Interesting"),
      b("applied", "✓", "Applied"), b("hide", "✕", "Hide")));
  }
  return li;
}

async function setMark(key, mark) {
  try {
    const r = await fetch("api/marks", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({key, mark})});
    if (r.ok) { marks = await r.json(); render(); }
  } catch (e) { alert("Could not save the mark. Is the local server still running?"); }
}

function header() {
  const s = D.summary || {};
  const n = D.jobs.length, fresh = D.jobs.filter(isNew).length;
  document.getElementById("status").textContent =
    (D.last_run ? "Last run " + D.last_run.replace("T", " ").replace("Z", " UTC") : "No run yet") +
    " · " + n + " open jobs · " + fresh + " new" +
    (live ? " · marks on" : " · read-only");
  const links = document.querySelector("#links ul");
  links.replaceChildren(...(D.links || []).map(l => el("li", {},
    el("a", {href: safeUrl(l.url), target: "_blank", rel: "noopener"}, l.name),
    l.note ? el("span", {}, " " + l.note) : null)));
  if (!(D.links || []).length) document.getElementById("links").hidden = true;
  const failed = s.boards_failed || [];
  document.getElementById("foot").textContent = s.run ?
    `Run took ${s.seconds}s: ${s.postings} postings read, ${s.kept} kept, ${s.boards_ok} sources OK` +
    (failed.length ? `, ${failed.length} failed (${failed.slice(0, 8).join(", ")}${failed.length > 8 ? ", ..." : ""})` : "") + "." : "";
}

document.getElementById("q").addEventListener("input", e => { q = e.target.value.trim().toLowerCase(); render(); });

(async () => {
  try {
    const r = await fetch("api/marks", {cache: "no-store"});
    if (r.ok && (r.headers.get("Content-Type") || "").includes("json")) { marks = await r.json(); live = true; }
  } catch (e) {}
  header();
  render();
})();
</script>
</body>
</html>
"""
