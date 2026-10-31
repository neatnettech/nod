"""Self contained, printable HTML sprint report for one cycle: summary, breakdown, cuttable task cards."""
from datetime import date
from html import escape

from nod.application.services import is_overdue
from nod.domain.enums import Priority, WorkItemStatus

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
footer { margin-top: 40px; color: var(--muted); font-size: 11px; text-transform: uppercase; }
@page { size: A4 landscape; margin: 12mm; }
@media print {
  * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  .page { margin: 0; border: none; padding: 0; max-width: none; }
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


def render_cycle(project, cycle, items, modules) -> str:
    module_name = {m.id: m.name for m in modules}
    items = sorted(items, key=lambda x: (STATUS_ORDER.index(x.status), PRIORITY_ORDER.index(x.priority), x.sequence_id))
    live = [x for x in items if x.status != WorkItemStatus.CANCELLED]
    total_h = sum(x.estimate or 0 for x in live)
    done = [x for x in live if x.status == WorkItemStatus.DONE]
    done_h = sum(x.estimate or 0 for x in done)
    # progress by estimate when there are estimates, else by item count
    pct = round(100 * (done_h / total_h if total_h else len(done) / len(live) if live else 0))

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
        foot = [f'<span class="badge type">{x.type.value}</span>']
        if x.priority != Priority.NO_PRIORITY:
            foot.append(f'<span class="badge p-{x.priority.value}">{x.priority.value}</span>')
        if x.estimate:
            foot.append(f'<span class="info">{_hours(x.estimate)}</span>')
        if x.due_date:
            due = f"due {escape(x.due_date)}"
            foot.append(f'<span class="overdue">{due}</span>' if is_overdue(x) else f'<span class="info">{due}</span>')
        if x.branch_name:
            foot.append(f'<span class="pill" title="{escape(x.branch_name)}">⎇ {escape(x.branch_name)}</span>')
        return (
            f'<div class="note {x.status.value}" style="background:{note_colour[x.module_id]}">'
            f'<div class="id"><span>{escape(x.identifier)}</span>'
            f'<span class="badge s-{x.status.value}">{x.status.value.replace("_", " ")}</span></div>'
            f'<div class="t">{escape(x.title)}</div>'
            f'<div class="foot">{"".join(foot)}</div></div>'
        )

    board = f'<div class="legend">{legend}</div><div class="board">{"".join(note(x) for x in items)}</div>'
    dates = f"{cycle.start_date or '?'} to {cycle.end_date or '?'}"
    description = f'<p class="dim">{escape(cycle.description)}</p>' if cycle.description else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(project.identifier)} · {escape(cycle.name)}</title>
<style>{CSS}</style></head>
<body><div class="page">
<h1>{escape(project.identifier)} / {escape(cycle.name)}</h1>
<div class="meta"><span class="chip">{escape(dates)}</span>{cycle.status.value} · generated {date.today().isoformat()}</div>
{description}
<h2><span class="chip">01</span>Summary</h2>
<div class="stats">
{stat("Items", len(live))}{stat("Estimate", _hours(total_h))}{stat("Done", _hours(done_h) if total_h else len(done))}{stat("Complete", f"{pct}%", hl=True)}
</div>
<h2><span class="chip">02</span>Breakdown</h2>
<div class="meters">
<div class="panel"><div class="head">Status<small>items, hours</small></div><div class="body">{_meters(by_status, busiest)}</div></div>
<div class="panel"><div class="head">Modules<small>items, hours</small></div><div class="body">{_meters(by_module, None)}</div></div>
</div>
<h2><span class="chip">03</span>Cards</h2>
{board}
<footer>Source: nod · {escape(project.name)}</footer>
</div></body></html>
"""
