"""Self contained, printable HTML sprint report for one cycle: summary, breakdown, cuttable task cards."""
from datetime import timezone
from html import escape
from urllib.parse import quote

from nod.application.services import is_overdue, stage_seconds, today
from nod.domain.enums import CycleStatus, Priority, WorkItemStatus

PRIORITY_ORDER = list(Priority)
STATUS_ORDER = list(WorkItemStatus)
# sticky note pastels, one per module
NOTE_COLOURS = ("#fbe38a", "#f9c5c0", "#bfe0f2", "#cbe8b5", "#fcd1a4", "#ddd0f0")

CSS = """
:root { --paper: #fff; --ink: #111; --accent: #f0cf5a; --accent-soft: #fdf3d0; --muted: #8a8a85; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
  font: 13px/1.45 "JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace; }
.page { max-width: 1180px; margin: 32px auto; padding: 40px 48px; border: 1.5px solid var(--ink); }
h1 { font-size: 28px; margin: 0; text-transform: uppercase; letter-spacing: .02em; }
.chip { display: inline-block; background: var(--accent); padding: 2px 8px; font-weight: 700; }
.meta { color: var(--muted); margin-top: 8px; }
.meta .chip { color: var(--ink); margin-right: 8px; }
h2 { display: inline-flex; gap: 12px; align-items: center; font-size: 18px; text-transform: uppercase;
  margin: 40px 0 20px; padding-bottom: 6px; border-bottom: 2.5px solid var(--ink); }
h2 .chip { font-size: 12px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.panel { border: 1.5px solid var(--ink); background: #fff; }
.panel > .head { border-bottom: 1.5px solid var(--ink); padding: 6px 12px; font-weight: 700; text-transform: uppercase; }
.panel > .head small { font-weight: 400; color: var(--muted); text-transform: none; margin-left: 6px; }
.panel > .body { padding: 14px 12px; }
.big { font-size: 30px; font-weight: 700; }
.big.hl { background: var(--accent); padding: 0 8px; }
.meters { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.meter { display: grid; grid-template-columns: 130px 1fr 110px; gap: 14px; align-items: center; margin: 10px 0; }
.label { border: 1.5px solid var(--ink); padding: 6px 4px; text-align: center; font-weight: 700; text-transform: uppercase; font-size: 11px; }
.label.on { background: var(--accent); }
.track { height: 18px; border: 1px solid var(--muted); background: #fff; }
.fill { height: 100%; background: var(--muted); }
.fill.on { background: var(--ink); }
.legend { margin: -6px 0 16px; font-size: 11px; text-transform: uppercase; }
.legend span { display: inline-block; width: 12px; height: 12px; border: 1.5px solid var(--ink); vertical-align: -2px; margin: 0 6px 0 14px; }
.legend span:first-child { margin-left: 0; }
.board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
/* flat, square cards with gaps between them, so a printed sheet cuts cleanly */
.note { border: 1.5px solid var(--ink); padding: 12px 14px 11px; min-height: 190px;
  display: flex; flex-direction: column; gap: 9px; break-inside: avoid; }
.note .id { font-weight: 700; font-size: 13px; align-items: center; display: flex; justify-content: space-between; }
.note .t { font-size: 15px; line-height: 1.4; flex: 1; overflow-wrap: anywhere; }
.note .foot { font-size: 11px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 5px; text-transform: uppercase; }
.badge { border: 1.5px solid var(--ink); background: #fff; padding: 0 5px; font-weight: 700; font-size: 10.5px; line-height: 17px; }
.badge.type { background: transparent; }
.badge.p-urgent { background: var(--ink); color: var(--accent); border-color: var(--ink); }
.badge.p-high { background: var(--ink); color: #fff; }
.badge.p-low { color: var(--muted); border-color: var(--muted); }
.pill { border: 1.5px solid var(--ink); border-radius: 999px; background: #fff; padding: 0 9px; font-size: 10.5px; line-height: 17px;
  text-transform: none; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.info { opacity: .75; }
.badge.s-in_progress { background: var(--accent); }
.badge.s-done { border-style: dashed; }
.note.cancelled .t { text-decoration: line-through; }
.overdue { background: var(--ink); color: var(--accent); padding: 0 4px; font-weight: 700; }
.dim { color: var(--muted); }
.empty { color: var(--muted); text-transform: uppercase; }
a { color: inherit; }
/* a whole card or line is the link to its item page */
.note, .line { position: relative; }
.item-link { text-decoration: none; }
.item-link::after { content: ""; position: absolute; inset: 0; }
.note:has(.item-link):hover, .line:has(.item-link):hover { outline: 2.5px solid var(--ink); outline-offset: 1px; cursor: pointer; }
.facts { display: grid; grid-template-columns: 130px 1fr; gap: 8px 14px; align-items: baseline; }
.facts dt { color: var(--muted); text-transform: uppercase; font-size: 11px; }
.facts dd { margin: 0; overflow-wrap: anywhere; position: relative; }  /* keeps a stretched item link inside its row */
.prose { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.55; }
.two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.6fr); gap: 16px; align-items: start; }
.crumbs { margin-bottom: 14px; text-transform: uppercase; font-size: 11px; }
.cycle { display: grid; grid-template-columns: minmax(160px, 1.4fr) 90px 190px 1fr 220px; gap: 14px; align-items: center;
  padding: 8px 12px; border: 1.5px solid var(--ink); margin-top: -1.5px; }
.cycle.on { background: var(--accent-soft); }
.cycle .name { font-weight: 700; text-transform: uppercase; overflow-wrap: anywhere; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; align-items: start; }
.head.on { background: var(--accent); }
.line { padding: 5px 0; border-top: 1px solid #ddd; overflow-wrap: anywhere; }
.line:first-child { border-top: none; padding-top: 0; }
.line .badge, .line .pill { display: inline-block; vertical-align: middle; margin-left: 4px; }
footer { margin-top: 40px; color: var(--muted); font-size: 11px; text-transform: uppercase; }
/* live dashboard only: moves between renders, what just changed, connection state */
::view-transition-group(*) { animation-duration: .5s; animation-timing-function: cubic-bezier(.2, .8, .2, 1); }
.changed { animation: flash 2.4s ease-out; }
@keyframes flash { 0%, 35% { box-shadow: 0 0 0 4px var(--ink), 0 0 0 9px var(--accent); } 100% { box-shadow: 0 0 0 0 transparent; } }
@keyframes pulse { 50% { opacity: .2; } }
.note .badge.s-in_progress::before, #live i { content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--ink); margin-right: 5px; animation: pulse 1.4s ease-in-out infinite; }
#live { position: fixed; top: 12px; right: 16px; z-index: 2; border: 1.5px solid var(--ink); background: var(--accent);
  padding: 2px 9px; font-weight: 700; font-size: 11px; text-transform: uppercase; }
#live.off { background: var(--ink); color: #fff; }
#live.off i { background: #fff; animation: none; }
#feed { position: fixed; bottom: 12px; right: 16px; z-index: 2; width: 330px; font-size: 11px; }
#feed a { display: block; border: 1.5px solid var(--ink); background: #fff; padding: 4px 9px; margin-top: -1.5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-decoration: none; }
#feed a:first-child { background: var(--accent-soft); font-weight: 700; }
#feed a:hover { background: var(--accent); }
@media (prefers-reduced-motion: reduce) {
  *, ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; }
}
@page { size: A4 landscape; margin: 12mm; }
@media print {
  * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  .page { margin: 0; border: none; padding: 0; max-width: none; }
  #live, #feed { display: none; }
}
"""


def _hours(value: float) -> str:
    return f"{round(value, 1):g}h"


def _meters(rows: list[tuple[str, int, float]], highlight: str | None) -> str:
    """rows: (label, count, hours). Bar length is the share of items."""
    total = sum(count for _, count, _ in rows) or 1
    out = []
    for label, count, hours in rows:
        on = " on" if label == highlight else ""
        out.append(
            f'<div class="meter"><div class="label{on}">{escape(label)}</div>'
            f'<div class="track"><div class="fill{on}" style="width:{count / total * 100:.1f}%"></div></div>'
            f"<div>{count} · {_hours(hours)}</div></div>"
        )
    return "".join(out)


# ponytail: refetches the whole page every 1.5s and swaps it in when it changed; switch to SSE if this ever gets heavy.
# Items carry a view-transition-name, so the browser animates each one from its old place to its new one.
LIVE_SCRIPT = """<div id="live"><i></i><span>live</span></div>
<script>
const badge = document.getElementById("live");
const states = () => new Map([...document.querySelectorAll("[data-id]")].map(e => [e.dataset.id, e.dataset.status]));
const online = on => { badge.className = on ? "" : "off"; badge.lastChild.textContent = on ? "live" : "offline"; };
let seen;
setInterval(async () => {
  try {
    const response = await fetch(location.href, {cache: "no-store"});
    if (!response.ok) throw new Error(response.status);
    const text = await response.text();
    online(true);
    if (seen !== undefined && text !== seen) {
      const next = new DOMParser().parseFromString(text, "text/html"), before = states();
      const swap = () => { document.querySelector(".page").replaceWith(next.querySelector(".page")); document.title = next.title; };
      if (document.startViewTransition) await document.startViewTransition(swap).updateCallbackDone; else swap();
      for (const [id, status] of states())
        if (before.get(id) !== status)
          document.querySelectorAll(`[data-id="${CSS.escape(id)}"]`).forEach(e => e.classList.add("changed"));
    }
    seen = text;
  } catch { online(false); }
}, 1500);
</script>"""


def _pct(items) -> int:
    """Share done, by estimate when there are estimates, else by item count. Cancelled items do not count."""
    live = [x for x in items if x.status != WorkItemStatus.CANCELLED]
    done = [x for x in live if x.status == WorkItemStatus.DONE]
    total_h = sum(x.estimate or 0 for x in live)
    done_h = sum(x.estimate or 0 for x in done)
    return round(100 * (done_h / total_h if total_h else len(done) / len(live) if live else 0))


def _span(seconds: float) -> str:
    """A duration at the coarsest unit that still says something: 40s, 25m, 3.5h, 2.1d."""
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{round(seconds / size, 1):g}{unit}"
    return f"{round(seconds)}s"


def _cycle_time(items, worked=None) -> str:
    """Average time from first start to completion, over the items that recorded both; empty when none did.
    worked (seconds in progress by identifier, from the status history) adds the average without hold time."""
    done = [x for x in items if x.started_at and x.completed_at and x.completed_at >= x.started_at]
    if not done:
        return ""
    spans = [(x.completed_at - x.started_at).total_seconds() for x in done]
    text = f"avg {_span(sum(spans) / len(spans))} over {len(spans)}"
    active = [worked[x.identifier] for x in done if x.identifier in (worked or {})]
    return text + (f", worked {_span(sum(active) / len(active))}" if active else "")


def _move_text(change) -> str:
    return f"{change.from_status or 'new'} → {change.to_status}".replace("_", " ")


def _when(moment) -> str:
    """A UTC timestamp, labelled as such; the day is named only when it is not today."""
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%H:%M UTC" if utc.date().isoformat() == today() else "%Y-%m-%d %H:%M UTC")


def _note(x, colour: str, cycle_name: str | None = None, vt: str = "") -> str:
    """vt: prefix for a view-transition-name, unique per place an item shows on one page; empty for print."""
    foot = [f'<span class="badge type">{x.type.value}</span>']
    if x.priority != Priority.NO_PRIORITY:
        foot.append(f'<span class="badge p-{x.priority.value}">{x.priority.value}</span>')
    if x.estimate:
        foot.append(f'<span class="info">{_hours(x.estimate)}</span>')
    if x.due_date:
        due = f"due {escape(x.due_date)}"
        foot.append(f'<span class="overdue">{due}</span>' if is_overdue(x) else f'<span class="info">{due}</span>')
    if cycle_name:
        foot.append(f'<span class="info">{escape(cycle_name)}</span>')
    # a fixed start time, not a running clock: the page only changes when the work does
    if x.started_at and x.status == WorkItemStatus.IN_PROGRESS:
        foot.append(f'<span class="info">since {_when(x.started_at)}</span>')
    if x.plan_path:
        foot.append(f'<span class="badge" title="{escape(x.plan_path)}">plan</span>')
    if x.branch_name:
        foot.append(f'<span class="pill" title="{escape(x.branch_name)}">⎇ {escape(x.branch_name)}</span>')
    return (
        f'<div class="note {x.status.value}" data-id="{escape(x.identifier)}" data-status="{x.status.value}" '
        f'style="background:{colour}{f";view-transition-name:{vt}{x.sequence_id}" if vt else ""}">'
        f'<div class="id"><span>{escape(x.identifier)}</span>'
        f'<span class="badge s-{x.status.value}">{x.status.value.replace("_", " ")}</span></div>'
        f'<div class="t">{_link(x, escape(x.title)) if vt else escape(x.title)}</div>'
        f'<div class="foot">{"".join(foot)}</div></div>'
    )


def _link(x, label: str) -> str:
    return f'<a class="item-link" href="/item/{quote(x.identifier, safe="")}">{label}</a>'


def _line(x, vt: str = "", status: bool = False) -> str:
    """One linked item on one line. status adds its badge, for lists that mix statuses."""
    extra = ""
    if status:
        extra += f'<span class="badge s-{x.status.value}">{x.status.value.replace("_", " ")}</span>'
    if x.priority in (Priority.URGENT, Priority.HIGH):
        extra += f'<span class="badge p-{x.priority.value}">{x.priority.value}</span>'
    if is_overdue(x):
        extra += f'<span class="overdue">due {escape(x.due_date)}</span>'
    if x.branch_name and x.status == WorkItemStatus.IN_PROGRESS:
        extra += f'<span class="pill">⎇ {escape(x.branch_name)}</span>'
    name = f' style="view-transition-name:{vt}{x.sequence_id}"' if vt else ""
    return (
        f'<div class="line" data-id="{escape(x.identifier)}" data-status="{x.status.value}"{name}>'
        f"{_link(x, f'<b>{escape(x.identifier)}</b> {escape(x.title)}')}{extra}</div>"
    )


def _columns(items) -> str:
    """Items as one column per status that has any, each a list of compact lines."""
    cols = []
    for status in STATUS_ORDER:
        group = sorted((x for x in items if x.status == status), key=lambda x: (PRIORITY_ORDER.index(x.priority), x.sequence_id))
        if not group:
            continue
        lines = [_line(x, vt="l") for x in group]
        on = " on" if status == WorkItemStatus.IN_PROGRESS else ""
        cols.append(
            f'<div class="panel"><div class="head{on}">{status.value.replace("_", " ")}<small>{len(group)}</small></div>'
            f'<div class="body">{"".join(lines)}</div></div>'
        )
    return f'<div class="cols">{"".join(cols)}</div>' if cols else '<p class="empty">No items</p>'


def render_item(project, item, module=None, cycle=None, parent=None, children=(), needs=(), unblocks=(), history=()) -> str:
    """Live detail page of one work item for `nod serve`: facts, description, epic, children, dependencies,
    and the recorded status history with the time each finished stage took."""
    x = item
    facts = [
        ("Status", f'<span class="badge s-{x.status.value}">{x.status.value.replace("_", " ")}</span>'),
        ("Type", x.type.value),
        ("Priority", x.priority.value.replace("_", " ")),
        ("Module", escape(module.name) if module else '<span class="dim">none</span>'),
        ("Cycle", f'<a href="/cycle/{cycle.slug}">{escape(cycle.name)}</a>' if cycle else '<a href="/unplanned">none</a>'),
    ]
    if x.estimate:
        facts.append(("Estimate", _hours(x.estimate)))
    if x.due_date:
        facts.append(("Due", f'<span class="overdue">{escape(x.due_date)} overdue</span>' if is_overdue(x) else escape(x.due_date)))
    for label, moment in (("Created", x.created_at), ("Started", x.started_at), ("Completed", x.completed_at)):
        if moment:
            facts.append((label, _when(moment)))
    if x.started_at and x.completed_at and x.completed_at >= x.started_at:
        facts.append(("Cycle time", _span((x.completed_at - x.started_at).total_seconds())))
    if x.created_at and x.completed_at and x.completed_at >= x.created_at:
        facts.append(("Lead time", _span((x.completed_at - x.created_at).total_seconds())))
    if x.branch_name:
        facts.append(("Branch", f'<span class="pill">⎇ {escape(x.branch_name)}</span>'))
    if x.from_branch or x.to_branch:
        facts.append(("Flow", f"{escape(x.from_branch or '?')} → {escape(x.to_branch or '?')}"))
    for status, seconds in stage_seconds(history).items():
        if status in ("in_progress", "hold", "todo"):
            facts.append((f"Time {status.replace('_', ' ')}", _span(seconds)))
    if parent:
        facts.append(("Epic", _link(parent, f"<b>{escape(parent.identifier)}</b> {escape(parent.title)}")))
    if x.plan_path:
        facts.append(("Plan", escape(x.plan_path)))
    if x.memory_path:
        facts.append(("Memory", escape(x.memory_path)))
    rows = "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts)
    description = f'<div class="prose">{escape(x.description)}</div>' if x.description else '<p class="empty">No description</p>'

    def listing(number, title, group):
        if not group:
            return ""
        done = sum(1 for g in group if g.status == WorkItemStatus.DONE)
        return (
            f'<h2><span class="chip">{number:02d}</span>{title}</h2>'
            f'<div class="panel"><div class="head">{done}/{len(group)} done</div>'
            f'<div class="body">{"".join(_line(g, status=True) for g in group)}</div></div>'
        )

    groups = [(t, g) for t, g in (("Children", children), ("Needs first", needs), ("Unblocks", unblocks)) if g]
    lists = "".join(listing(i, title, group) for i, (title, group) in enumerate(groups, start=2))
    if history:
        moves = "".join(
            f'<div class="line"><b>{c.at.strftime("%Y-%m-%d %H:%M:%S")} UTC</b> {_move_text(c)}</div>' for c in reversed(history)
        )
        lists += (
            f'<h2><span class="chip">{len(groups) + 2:02d}</span>History</h2>'
            f'<div class="panel"><div class="head">{len(history)} moves<small>newest first</small></div><div class="body">{moves}</div></div>'
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(x.identifier)} · {escape(x.title)}</title>
<style>{CSS}</style></head>
<body><div class="page">
<div class="crumbs"><a href="/">← {escape(project.identifier)} live</a></div>
<h1 data-id="{escape(x.identifier)}" data-status="{x.status.value}"><span class="chip">{escape(x.identifier)}</span> {escape(x.title)}</h1>
<h2><span class="chip">01</span>Details</h2>
<div class="two">
<div class="panel"><div class="head">Facts</div><div class="body"><dl class="facts">{rows}</dl></div></div>
<div class="panel"><div class="head">Description</div><div class="body">{description}</div></div>
</div>
{lists}
<footer>Source: nod · {escape(project.name)}</footer>
</div>{LIVE_SCRIPT}</body></html>
"""


def render_dashboard(project, cycles, items, modules, current=None, activity=(), worked=None) -> str:
    """Live overview for `nod serve`: what is in progress now, every cycle with its
    progress, and the items of each open cycle by status."""
    colour = {m.id: NOTE_COLOURS[i % len(NOTE_COLOURS)] for i, m in enumerate(modules)}
    cycles = sorted(cycles, key=lambda c: (c.start_date or "9999-99-99", c.name))
    cycle_name = {c.id: c.name for c in cycles}
    of = {c.id: [x for x in items if x.cycle_id == c.id] for c in cycles}
    unplanned = [x for x in items if x.cycle_id is None]

    doing = "".join(
        _note(x, colour.get(x.module_id, "#fff"), cycle_name.get(x.cycle_id, "no cycle"), vt="n")
        for x in items if x.status == WorkItemStatus.IN_PROGRESS
    )
    now = f'<div class="board">{doing}</div>' if doing else '<p class="empty">Nothing in progress</p>'

    def row(name, href, status, dates, group, on=False):
        live = [x for x in group if x.status != WorkItemStatus.CANCELLED]
        done = sum(1 for x in live if x.status == WorkItemStatus.DONE)
        active = sum(1 for x in live if x.status == WorkItemStatus.IN_PROGRESS)
        pct = _pct(group)
        mark = ' <span class="chip">current</span>' if on else ""
        return (
            f'<div class="cycle{" on" if on else ""}"><div class="name"><a href="{href}">{escape(name)}</a>{mark}</div>'
            f"<div>{status}</div><div>{escape(dates)}</div>"
            f'<div class="track"><div class="fill on" style="width:{pct}%;view-transition-name:{href.strip("/").replace("/", "-")}"></div></div>'
            f"<div>{pct}% · {done}/{len(live)} done · {active} doing"
            f"{f'<br><span class=dim>cycle time {average}</span>' if (average := _cycle_time(group, worked)) else ''}</div></div>"
        )

    rows = [
        row(c.name, f"/cycle/{c.slug}", c.status.value, f"{c.start_date or '?'} to {c.end_date or '?'}", of[c.id],
            on=bool(current and c.id == current.id))
        for c in cycles
    ]
    if unplanned:
        rows.append(row("No cycle", "/unplanned", "", "", unplanned))
    if not cycles:
        rows.append('<p class="empty">No cycles yet: nod cycle add "Sprint 1" --start 2026-10-01 --end 2026-10-14</p>')

    # items per cycle: the current one first, finished cycles only through their link above
    open_ = [c for c in cycles if c.status in (CycleStatus.ACTIVE, CycleStatus.UPCOMING) or (current and c.id == current.id)]
    open_.sort(key=lambda c: not (current and c.id == current.id))
    sections = [
        f'<h2><span class="chip">{i:02d}</span><a href="/cycle/{c.slug}">{escape(c.name)}</a></h2>{_columns(of[c.id])}'
        for i, c in enumerate(open_, start=2)
    ]
    if unplanned:
        sections.append(f'<h2><span class="chip">{len(open_) + 2:02d}</span><a href="/unplanned">No cycle</a></h2>{_columns(unplanned)}')

    # newest first; each row keeps its own transition name, so a new move pushes the older ones down
    feed = "".join(
        f'<a href="/item/{quote(c.identifier, safe="")}" style="view-transition-name:e{c.id.replace("-", "")}">'
        f"{c.at.strftime('%H:%M:%S')} UTC · {escape(c.identifier)} · {_move_text(c)}</a>"
        for c in reversed(activity)
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(project.identifier)} · live</title>
<style>{CSS}</style></head>
<body><div class="page">
<h1>{escape(project.identifier)} / Live</h1>
<div class="meta"><span class="chip">{len(items)} items</span>{escape(project.name)} · {today()} UTC{f" · cycle time {average}" if (average := _cycle_time(items, worked)) else ""}</div>
<h2><span class="chip">00</span>Now</h2>
{now}
<h2><span class="chip">01</span>Cycles</h2>
{"".join(rows)}
{"".join(sections)}
<div id="feed">{feed}</div>
<footer>Source: nod · {escape(project.name)}</footer>
</div>{LIVE_SCRIPT}</body></html>
"""


def render_cycle(project, cycle, items, modules, live: bool = False) -> str:
    """live adds a link home, a Now section (in progress cards) and self reload, for `nod serve`."""
    module_name = {m.id: m.name for m in modules}
    items = sorted(items, key=lambda x: (STATUS_ORDER.index(x.status), PRIORITY_ORDER.index(x.priority), x.sequence_id))
    live_items = [x for x in items if x.status != WorkItemStatus.CANCELLED]
    total_h = sum(x.estimate or 0 for x in live_items)
    done = [x for x in live_items if x.status == WorkItemStatus.DONE]
    done_h = sum(x.estimate or 0 for x in done)
    pct = _pct(items)

    def stat(head, value, hl=False):
        return f'<div class="panel"><div class="head">{head}</div><div class="body"><span class="big{" hl" if hl else ""}">{value}</span></div></div>'

    by_status = [
        (s.value.replace("_", " "), sum(1 for x in items if x.status == s), sum(x.estimate or 0 for x in items if x.status == s))
        for s in STATUS_ORDER
    ]
    busiest = max(by_status, key=lambda r: r[1])[0] if items else None
    module_ids = list(dict.fromkeys(x.module_id for x in items))
    by_module = [
        (module_name.get(mid, "no module"), sum(1 for x in items if x.module_id == mid), sum(x.estimate or 0 for x in items if x.module_id == mid))
        for mid in module_ids
    ]

    # one sticky note colour per module, in the order modules first appear
    note_colour = {mid: NOTE_COLOURS[i % len(NOTE_COLOURS)] for i, mid in enumerate(module_ids)}
    legend = "".join(
        f'<span style="background:{note_colour[mid]}"></span>{escape(module_name.get(mid, "no module"))}'
        for mid in module_ids
    )

    def note(x):
        return _note(x, note_colour[x.module_id], vt="b" if live else "")

    board = f'<div class="legend">{legend}</div><div class="board">{"".join(note(x) for x in items)}</div>'
    dates = f"{cycle.start_date or '?'} to {cycle.end_date or '?'}"
    now = ""
    if live:
        doing = "".join(_note(x, note_colour[x.module_id], vt="n") for x in items if x.status == WorkItemStatus.IN_PROGRESS)
        now = '<div class="crumbs"><a href="/">← all cycles</a></div><h2><span class="chip">00</span>Now</h2>' + (
            f'<div class="board">{doing}</div>' if doing else '<p class="empty">Nothing in progress</p>'
        )
    description = f'<p class="dim">{escape(cycle.description)}</p>' if cycle.description else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(project.identifier)} · {escape(cycle.name)}</title>
<style>{CSS}</style></head>
<body><div class="page">
<h1>{escape(project.identifier)} / {escape(cycle.name)}</h1>
<div class="meta"><span class="chip">{escape(dates)}</span>{cycle.status.value} · generated {today()}</div>
{description}
{now}
<h2><span class="chip">01</span>Summary</h2>
<div class="stats">
{stat("Items", len(live_items))}{stat("Estimate", _hours(total_h))}{stat("Done", _hours(done_h) if total_h else len(done))}{stat("Complete", f"{pct}%", hl=True)}
</div>
<h2><span class="chip">02</span>Breakdown</h2>
<div class="meters">
<div class="panel"><div class="head">Status<small>items, hours</small></div><div class="body">{_meters(by_status, busiest)}</div></div>
<div class="panel"><div class="head">Modules<small>items, hours</small></div><div class="body">{_meters(by_module, None)}</div></div>
</div>
<h2><span class="chip">03</span>Cards</h2>
{board}
<footer>Source: nod · {escape(project.name)}</footer>
</div>{LIVE_SCRIPT if live else ""}</body></html>
"""
