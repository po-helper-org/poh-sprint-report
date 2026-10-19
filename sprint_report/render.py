"""Отчёт команды — 2 книжные страницы A4 (HTML для печати в PDF).

Стр. 1 — пульс команды (прогноз спринта, закрываем в день, в работе одновременно, где ждут) → «Успеем к …?»:
сгорание и решения техлида на сегодня (номера задач — ссылки в Jira) → сроки и обещания → эпики в спринте.
Стр. 2 — команда, «Стоит дольше всего» и Kanban-доска.
Акценты: цвет — только на маркерах, полосах и кромках; в каждом блоке выделен один худший элемент.

render(model, ops, team) → HTML; teams(ops) — команды; summary() — цифры для подписи к отправке.
"""
import datetime as dt
import html
import math
import re

WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MON = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
INK, SEC, MUTED, LINE, GRID, SURF = "#15171C", "#4A505C", "#8B919C", "#E3E5E9", "#EFF0F3", "#F5F6F8"
RED, RED_MID, RED_LOW = "#D1342B", "#E8857D", "#F2C4C0"
AMBER, AMBER_LOW = "#C27803", "#F3DDB5"
DONE, WIP, TODO, OK = "#2F5BD3", "#B9C9F2", "#E3E5E9", "#2E8B57"
STALE_DAYS = 3
BLOCK_BINS = [(10, None, "10+ дн."), (5, 10, "5–9 дн."), (3, 5, "3–4 дн.")]   # [10;∞), [5;10), [3;5) — без пересечений
TOP_LONG, TOP_DATES, CARD_LIMIT, DONE_LIMIT = 8, 10, 8, 16
CHIP_LIMIT, BIG_SP, WIP_PER_PERSON = 14, 8, 1.5      # номеров в строке решения; от скольких SP задачу дробить
TL_PAST, TL_FUTURE = 21, 14          # шкала таймлайна, дней от сегодня
_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_KEY_HEAD = re.compile(r"^\s*[A-Z][A-Z0-9]+-\d+\s*:\s*")
_PREFIX = re.compile(r"^\s*(?:\[[^\]]+\]\s*|\(?[A-Za-z]{2,6}\)?\s*:\s*|СТ\.?\s+|ST\.?\s+|[-–—·]\s*)+")


def e(s):
    return html.escape(str(s or ""))


def d(iso):
    return dt.date.fromisoformat(iso[:10])


def dm(x):
    x = d(x) if isinstance(x, str) else x
    return f"{x.day:02d}.{x.month:02d}" if x else ""


def plural(n, one, few, many):
    n10, n100 = n % 10, n % 100
    return one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many


def workdays(a, b):
    n = 0
    while a <= b:
        n += a.weekday() < 5
        a += dt.timedelta(days=1)
    return n


def uniq(rows, key):
    seen, out = set(), []
    for r in rows:
        if r[key] not in seen:
            seen.add(r[key])
            out.append(r)
    return out


def clean(title):
    """Название без служебных префиксов [BE], СТ., (PHP) — роль показывается отдельно."""
    return _PREFIX.sub("", str(title or "")).strip() or str(title or "")


def role(title):
    m = re.match(r"\s*\[([A-Za-z]{2,6})\]", str(title or ""))
    return m.group(1).upper() if m else ""


def surname(who):
    return str(who or "").split()[0] if who else ""


def teams(ops):
    return [t["team"] for t in ops["teams"]]


# ---------- расчёты ----------

def sprint_state(t, today):
    pts = [b for b in t["burn"] if b["date"] <= today.isoformat()]
    last = pts[-1] if pts else {"remaining": 0, "scope": 0, "closed": 0, "date": t["start"]}
    start, end = d(t["start"]), d(t["end"])
    first = t["burn"][0]["scope"] if t["burn"] else 0
    ideal = round(first * (1 - min(1, (today - start).days / max(1, (end - start).days))))
    return {"closed": last["closed"], "scope": last["scope"], "remaining": last["remaining"], "first": first,
            "ideal": ideal, "behind": last["remaining"] - ideal, "start": start, "end": end,
            "left": workdays(today + dt.timedelta(days=1), end), "last": last}


def key_dates(model, t, today):
    """Обещания команды руководителю («мне обещали» от участников команды) и сроки эпиков в работе.
    У обещания — статус задачи Jira, если её номер есть в тексте; у эпика — ответственный и доля готовых историй."""
    names = {p["short"].split()[0].lower(): p["short"] for p in t["people"]}
    status = {x["key"]: x["status"] for x in model["tasks"] + model["blockers"] if x["team"] == t["team"]}
    status.update({x["key"]: "Готово" for x in model["done"] if x["team"] == t["team"]})
    status.update({x["key"]: "Не начато" for x in t.get("not_started_items", []) if x["key"] not in status})
    out = []
    for c in model["promises"]:
        who = next((names[w] for w in (x.lower().strip(".,()") for x in str(c["who"]).split()) if w in names), None)
        if c["side"] == "them" and who:
            key = next(iter(_KEY.findall(c["what"])), "")
            out.append({"kind": "promise", "id": c["id"], "key": key, "what": _KEY_HEAD.sub("", c["what"]), "who": who,
                        "due": c.get("due"), "status": status.get(key, "")})
    for x in t["roadmap"]:
        if x.get("due") and (x["cats"]["todo"] or x["cats"]["work"]):
            out.append({"kind": "epic", "id": x["key"], "key": x["key"], "what": x["title"], "who": x.get("owner", ""),
                        "due": x["due"], "cats": x["cats"]})
    for r in out:
        r["left"] = (d(r["due"]) - today).days if r["due"] else None
    return sorted(out, key=lambda r: (r["left"] is None, r["left"] if r["left"] is not None else 0))


def summary(model, ops, team):
    today = d(model["day"])
    t = next(x for x in ops["teams"] if x["team"] == team)
    blocked = sorted(uniq([b for b in model["blockers"] if b["team"] == team], "key"), key=lambda b: -(b["days"] or 0))
    tasks = uniq([x for x in model["tasks"] if x["team"] == team], "key")
    dates = key_dates(model, t, today)
    return {"today": today, "t": t, "s": sprint_state(t, today), "blocked": blocked, "tasks": tasks, "dates": dates,
            "stale": sum(1 for x in tasks if (x["days"] or 0) > STALE_DAYS),
            "long": sum(1 for b in blocked if (b["days"] or 0) >= STALE_DAYS),
            "late": sum(1 for r in dates if r["left"] is not None and r["left"] < 0),
            "bins": [sum(1 for b in blocked if (b["days"] or 0) >= lo and (hi is None or (b["days"] or 0) < hi)) for lo, hi, _ in BLOCK_BINS],
            "prefix": max(["-"] + [x["key"].split("-")[0] for x in t.get("open_items", [])],
                          key=lambda p: sum(1 for x in t.get("open_items", []) if x["key"].startswith(p + "-"))),
            "jira": next((x["jira"] for x in model["meta"] if x["team"] == team), ""),
            "fresh": next((x["collectedAt"] for x in model["meta"] if x["team"] == team), "")}


def block_color(days):
    return RED if days >= 5 else RED_MID if days >= 3 else RED_LOW


def link(m, key):
    return f'{m["jira"]}/browse/{key}' if m["jira"] else "#"


# ---------- стр. 1 ----------

def header(m, team, sub, page_label):
    today, fresh = m["today"], m["fresh"]
    stale_snap = bool(fresh) and d(fresh) < today - dt.timedelta(days=1)
    jira = f'<span class="{"amber" if stale_snap else ""}">Jira {dm(fresh[:10])} {e(fresh[11:16])}</span>' if fresh else ""
    return f"""<header class="hd"><div><span class="team">{e(team)}</span><span class="sub">{sub}</span></div>
<div class="when">{WD[today.weekday()]}, {today.day} {MON[today.month - 1]} · {jira}</div></header>"""


def delta(v, good_up, unit=""):
    """Изменение со вчера: ▲/▼, зелёным — если к лучшему."""
    if not v:
        return ""
    up = v > 0
    cls = "ok" if up == good_up else "bad"
    return f'<span class="dl {cls}">{"▲" if up else "▼"} {num(abs(v), 0 if float(v).is_integer() else 1)}{unit}</span>'


def spark(vals, kind, line=None, hot_last=True, W=120, H=30):
    """Мини-график по дням: столбики (закрыто) или линия (в работе); line — пунктир ориентира."""
    n = len(vals)
    top = max(vals + [line or 0, 1]) * 1.15
    y = lambda v: H - v / top * (H - 2)   # noqa: E731
    step = W / max(1, n)
    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="none" class="spk">']
    o.append(f'<line x1="0" x2="{W}" y1="{H - .5}" y2="{H - .5}" stroke="{LINE}" stroke-width="1"/>')
    if kind == "bars":
        for i, v in enumerate(vals):
            o.append(f'<rect x="{i * step + 1:.1f}" y="{y(v):.1f}" width="{step - 2:.1f}" height="{H - y(v):.1f}" '
                     f'fill="{DONE if i >= n - 5 else WIP}" rx="1"/>')
    else:
        pts = " ".join(f"{(i + .5) * step:.1f},{y(v):.1f}" for i, v in enumerate(vals))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
                 f'<circle cx="{(n - .5) * step:.1f}" cy="{y(vals[-1]):.1f}" r="2.4" fill="{INK}"/>')
    if line:
        o.append(f'<line x1="0" x2="{W}" y1="{y(line):.1f}" y2="{y(line):.1f}" stroke="{RED}" stroke-width="1" stroke-dasharray="3 2"/>')
    return "".join(o) + "</svg>"


def spark_label(vals, line, H=30):
    """Число у пунктира — отдельно от растянутого svg, чтобы не сплющилось."""
    top = max(vals + [line or 0, 1]) * 1.15
    return f'<span class="ln" style="bottom:{(line / top * (H - 2)) / H * 100:.0f}%">{num(line, 0 if float(line).is_integer() else 1)}</span>'


def kpis(m):
    """Пульс команды: прогноз спринта, пропускная способность, незавершённая работа, где задачи ждут."""
    t, s, unit = m["t"], m["s"], m["t"]["unit"]
    fc = forecast(m)
    tiles = []
    # 1. Прогноз: какую долю объёма закроем к концу при текущем темпе
    scope = max(1, fc["last"]["scope"]) if fc else 1
    pct = round((scope - fc["proj"]) / scope * 100) if fc else 0
    data_day = min(m["today"], d(m["fresh"])) if m["fresh"] else m["today"]
    pts = [b for b in t["burn"] if b["date"] <= data_day.isoformat()]
    prev = None
    if len(pts) > 2:
        f0, f1 = pts[0], pts[-2]
        pace0 = (f1["closed"] - f0["closed"]) / max(1, workdays(d(f0["date"]) + dt.timedelta(days=1), d(f1["date"])))
        left0 = workdays(d(f1["date"]) + dt.timedelta(days=1), s["end"])
        prev = round((f1["scope"] - max(0, f1["remaining"] - pace0 * left0)) / max(1, f1["scope"]) * 100)
    done_w = fc["last"]["closed"] / scope * 100 if fc else 0
    bar = (f'<div class="fbar"><i style="width:{done_w:.1f}%;background:{DONE}"></i>'
           f'<i class="hatch-b" style="width:{max(0, pct - done_w):.1f}%"></i><b style="left:{pct}%"></b></div>')
    tiles.append(("Прогноз спринта", f"{pct}", "%", delta(pct - prev if prev is not None else 0, True, " п.п."),
                  f'<div class="kz">{bar}</div>'))
    # 2. Пропускная способность: закрыто задач в день по дням спринта
    p = t.get("pulse") or {"days": [], "done": [], "wip": []}
    keep = [i for i, x in enumerate(p["days"]) if x >= t["start"]]
    done = [p["done"][i] for i in keep]
    wip = [p["wip"][i] for i in keep]
    last5, prev5 = done[-5:], done[-10:-5]
    rate = sum(last5) / max(1, len(last5))
    need = len(t.get("open_items", [])) / fc["left"] if fc and fc["left"] else None
    need = round(need, 1) if need else None
    tiles.append(("Закрываем в день", num(rate), "", (delta(round(rate - sum(prev5) / len(prev5), 1), True) if prev5 else ""),
                  f'<div class="kz">{spark(done, "bars", need)}{spark_label(done, need) if need else ""}</div>'))
    # 3. Незавершённая работа: задач в работе, ревью, отладке и блоке
    ppl = max(1, len(t["people"]))
    now = wip[-1] if wip else 0
    lim = round(ppl * WIP_PER_PERSON)
    tiles.append(("В работе одновременно", f"{now}", f" / {ppl} чел", delta(now - wip[-2] if len(wip) > 1 else 0, False),
                  f'<div class="kz">{spark(wip, "line", lim)}{spark_label(wip, lim)}</div>'))
    # 4. Где задачи ждут: средние дни без смены статуса по этапам
    stages = [("в блоке", [b["days"] or 0 for b in m["blocked"]]),
              ("в работе", [x["days"] or 0 for x in m["tasks"] if x.get("bucket") == "progress"]),
              ("ревью", [x["days"] or 0 for x in m["tasks"] if x.get("bucket") == "review"]),
              ("отладка", [x["days"] or 0 for x in m["tasks"] if x.get("bucket") == "testing"])]
    avg = [(n, sum(v) / len(v) if v else 0, len(v)) for n, v in stages]
    worst = max(avg, key=lambda r: r[1])
    mx = max(1, worst[1])
    rows = "".join(f'<div class="wr"><span class="{"hot" if (n, a, c) == worst else ""}">{n}</span>'
                   f'<i style="width:{a / mx * 100:.0f}%;background:{RED if (n, a, c) == worst else "#C9CDD4"}"></i></div>' for n, a, c in avg)
    tiles.append(("Где ждут дольше", num(worst[1]), " дн", "", f'<div class="kz wait">{rows}</div>'))
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="kl">{lbl}</div><div class="kv">{v}<span>{u}</span>{dl}</div>{viz}</div>'
        for lbl, v, u, dl, viz in tiles) + "</div>"


def longest(m):
    rows = [dict(b, kind="block") for b in m["blocked"] if (b["days"] or 0) >= STALE_DAYS]
    rows += [dict(x, kind="stale") for x in m["tasks"] if (x["days"] or 0) > STALE_DAYS]
    rows.sort(key=lambda r: -(r["days"] or 0))
    rows = rows[:TOP_LONG]
    fresh = sum(1 for b in m["blocked"] if (b["days"] or 0) < STALE_DAYS)
    if not rows:
        return '<div class="empty">Ни блоков от 3 дней, ни застоя</div>'
    mx = max(r["days"] for r in rows)
    top_block = next((r for r in rows if r["kind"] == "block"), None)
    out = []
    for r in rows:
        color = RED if r["kind"] == "block" else AMBER
        hot = r is top_block
        w = r["days"] / mx * 100
        out.append(f"""<a class="lrow" href="{link(m, r['key'])}"><span class="lt">{e(clean(r['title']))}</span><span class="lw">{e(r['who'])}</span>
<span class="lb"><i style="width:{w:.1f}%;background:{color}"></i><em class="{'hot' if hot else ''}" style="{'color:' + RED if hot else ''}">{r['days']} дн</em></span></a>""")
    tail = f'<div class="note">+{fresh} {plural(fresh, "блок", "блока", "блоков")} до {STALE_DAYS} дн</div>' if fresh else ""
    return '<div class="long">' + "".join(out) + "</div>" + tail


def forecast(m):
    """Успеем ли: темп — SP за рабочий день с начала спринта, нужный темп — остаток на оставшиеся дни,
    прогноз — сколько останется к концу при текущем темпе (линейно)."""
    t, s = m["t"], m["s"]
    data_day = min(m["today"], d(m["fresh"])) if m["fresh"] else m["today"]
    pts = [b for b in t["burn"] if b["date"] <= data_day.isoformat()]
    if not pts:
        return None
    first, last = pts[0], pts[-1]
    pace = (last["closed"] - first["closed"]) / max(1, workdays(d(first["date"]) + dt.timedelta(days=1), d(last["date"])))
    left = workdays(d(last["date"]) + dt.timedelta(days=1), s["end"])
    proj = max(0, round(last["remaining"] - pace * left))
    return {"pace": pace, "need": last["remaining"] / left if left else None, "left": left, "proj": proj,
            "last": last, "added": last["scope"] - first["scope"], "end": s["end"]}


def burndown(t, s, today, W=470, H=172, fc=None):
    L, R, T, B = 24, 56, 14, 16
    start, end = s["start"], s["end"]
    span = max(1, (end - start).days)
    burn = t["burn"]
    upto = fc["last"]["date"] if fc else today.isoformat()   # факт — до даты выгрузки Jira, дальше прогноз
    pts = [b for b in burn if b["date"] <= upto]
    top_v = max([b["scope"] for b in burn] + [1])
    step = max(5, math.ceil(top_v / 3 / 5) * 5)
    top = step * math.ceil(top_v / step)
    x = lambda day: L + (d(day) - start).days / span * (W - L - R)   # noqa: E731
    y = lambda v: T + (1 - v / top) * (H - T - B)   # noqa: E731
    o = [f'<svg viewBox="0 0 {W} {H}" width="100%">']
    day = start
    while day <= end:
        if day.weekday() >= 5:
            o.append(f'<rect x="{x(day.isoformat()):.1f}" y="{T}" width="{(W - L - R) / span:.1f}" height="{H - T - B}" fill="{SURF}"/>')
        day += dt.timedelta(days=1)
    for v in range(0, top + 1, step):
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>'
                 f'<text x="{L - 5}" y="{y(v) + 3:.1f}" text-anchor="end" class="ax">{v}</text>')
    if pts:   # объём — ступенькой
        sc = f"M{x(pts[0]['date']):.1f},{y(pts[0]['scope']):.1f}"
        for a, b in zip(pts, pts[1:]):
            sc += f" H{x(b['date']):.1f} V{y(b['scope']):.1f}"
        sc += f" H{x(end.isoformat()):.1f}"
        o.append(f'<path d="{sc}" fill="none" stroke="{SEC}" stroke-width="1"/>'
                 f'<text x="{W - R + 4:.1f}" y="{y(pts[-1]["scope"]) - 4:.1f}" class="ax">объём {pts[-1]["scope"]}</text>')
    first = burn[0]["scope"] if burn else top
    o.append(f'<line x1="{x(t["start"]):.1f}" y1="{y(first):.1f}" x2="{x(t["end"]):.1f}" y2="{y(0):.1f}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="3 3"/>')
    if pts:
        path = " ".join(f'{"M" if i == 0 else "L"}{x(b["date"]):.1f},{y(b["remaining"]):.1f}' for i, b in enumerate(pts))
        last = pts[-1]
        lx, ly = x(last["date"]), y(last["remaining"])
        o.append(f'<path d="{path}" fill="none" stroke="{DONE}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        if fc and fc["left"]:   # прогноз при текущем темпе — пунктир до конца спринта
            ex, ey = x(end.isoformat()), y(fc["proj"])
            o.append(f'<line x1="{x(fc["last"]["date"]):.1f}" y1="{y(fc["last"]["remaining"]):.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                     f'stroke="{DONE}" stroke-width="1.5" stroke-dasharray="4 3"/>'
                     f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="#fff" stroke="{DONE}" stroke-width="1.5"/>')
            if fc["proj"] > 0:   # не успеем: скобка от нуля до прогноза
                o.append(f'<path d="M{ex + 4:.1f},{y(0):.1f} H{ex + 8:.1f} V{ey:.1f} H{ex + 4:.1f}" fill="none" stroke="{RED}" stroke-width="1.3"/>'
                         f'<text x="{ex + 11:.1f}" y="{(y(0) + ey) / 2 + 4:.1f}" class="gap">≈{fc["proj"]}</text>')
        o.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.2" fill="{DONE}" stroke="#fff" stroke-width="1.5"/>'
                 f'<text x="{lx - 6:.1f}" y="{ly - 7:.1f}" text-anchor="end" class="val">{last["remaining"]}</text>'
                 f'<text x="{lx:.1f}" y="{H - 3}" text-anchor="middle" class="ax">{dm(last["date"])}</text>')
    o.append(f'<text x="{L}" y="{H - 3}" class="ax">{dm(start)}</text>'
             f'<text x="{x(end.isoformat()):.1f}" y="{H - 3}" text-anchor="end" class="ax">{dm(end)}</text></svg>')
    return "".join(o)


def num(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def tasks_word(n):
    return f"{n} {plural(n, 'задача', 'задачи', 'задач')}"


def descope(t, gap):
    """Кандидаты снять из спринта: не начатые, крупные первыми, пока не закроют разрыв прогноза."""
    pick, total = [], 0
    for x in t.get("not_started_items", []):
        if total >= gap or not x["sp"]:
            break
        pick.append(x)
        total += x["sp"]
    return pick, total


def chips(m, keys):
    """Задачи — номерами-ссылками; ключ целиком, только если проект не основной для команды."""
    prefix = m["prefix"]
    out = "".join(f'<a class="chip" href="{link(m, k)}">{e(k.split("-", 1)[1] if k.startswith(prefix + "-") else k)}</a>'
                  for k in keys[:CHIP_LIMIT])
    more = f'<span class="chip more">+{len(keys) - CHIP_LIMIT}</span>' if len(keys) > CHIP_LIMIT else ""
    return f'<div class="chips">{out}{more}</div>'


def decisions(m, fc):
    """Управленческие решения техлида: что сделать → какие задачи. Без пояснений — номера ведут в Jira."""
    t, unit = m["t"], m["t"]["unit"]
    stage = ("review", "testing")
    by_days = lambda xs: [x["key"] for x in sorted(xs, key=lambda x: -(x["days"] or 0))]   # noqa: E731
    blocked = {b["key"] for b in m["blocked"]}
    rows = [(RED, "Снять блоки", str(len(m["blocked"])), by_days(m["blocked"])),
            (DONE, "Провести ревью и отладку", "", by_days([x for x in m["tasks"] if x.get("bucket") in stage])),
            (AMBER, "Разморозить застой", "", by_days([x for x in m["tasks"] if (x["days"] or 0) > STALE_DAYS
                                                       and x.get("bucket") not in stage and x["key"] not in blocked]))]
    if fc and fc["proj"] > 0:
        pick, _ = descope(t, fc["proj"])
        rows.append((INK, "Не успеваем — оповестить PO", f"≈{fc['proj']} {unit}", [x["key"] for x in pick]))
    items = t.get("open_items", [])
    raw = [x["key"] for x in items if not x["sp"]] + [x["key"] for x in sorted(items, key=lambda x: -x["sp"]) if x["sp"] >= BIG_SP]
    rows.append((MUTED, "Оценить и декомпозировать", "", raw))
    out = []
    for c, title, note, keys in rows:
        if not keys:
            continue
        note = note if note and not note.isdigit() else str(len(keys))
        out.append(f'<div class="dr" style="border-color:{c}"><div class="dt"><b>{e(title)}</b><span>{e(note)}</span></div>{chips(m, keys)}</div>')
    return "".join(out) or '<div class="empty">Идём по графику — вмешательство не нужно</div>'


def sprint_block(m):
    t, s = m["t"], m["s"]
    fc = forecast(m)
    unit = t["unit"]
    head = ""
    if fc and fc["left"]:
        head = (f'<span class="verdict">нет · не хватит <b class="red">≈{fc["proj"]} {unit}</b></span>' if fc["proj"] > 0
                else '<span class="verdict">да · при текущем темпе</span>')
    return f"""<section><div class="bh"><h2>Успеем к {dm(s['end'])}?</h2>{head}</div>
<div class="row2"><div>{burndown(t, s, m["today"], W=440, H=230, fc=fc)}</div><div class="dec">{decisions(m, fc)}</div></div></section>"""


def deviation(left, worst):
    if left is None:
        return '<span class="dv">без срока</span>'
    if left < 0:
        return f'<span class="dv red{" hot" if left == worst else ""}">−{-left} дн</span>'
    if left == 0:
        return '<span class="dv amber">сегодня</span>'
    return f'<span class="dv">через {left} дн</span>'


def state(r):
    """Статус: у эпика — полоса готовых историй, у обещания — статус связанной задачи Jira."""
    if r["kind"] == "epic":
        c = r["cats"]
        tot = max(1, sum(c.values()))
        bar = "".join(f'<i style="width:{c[k] / tot * 100:.1f}%;background:{col}"></i>' for k, col in (("done", DONE), ("work", WIP)) if c.get(k))
        return f'<span class="sb">{bar}</span><span>{c["done"]}/{sum(c.values())}</span>'
    return f'<span>{e(r["status"])}</span>' if r["status"] else '<span class="muted">—</span>'


def timeline(m):
    rows = m["dates"][:TOP_DATES]
    if not rows:
        return '<div class="empty">Обещаний команды и сроков эпиков нет</div>'
    W, H, span = 150, 17, TL_PAST + TL_FUTURE   # пропорции ячейки 40×4.8 мм — иначе подписи сплющит
    x = lambda off: (max(-TL_PAST, min(TL_FUTURE, off)) + TL_PAST) / span * W   # noqa: E731
    today = m["today"]
    worst = min((r["left"] for r in rows if r["left"] is not None and r["left"] < 0), default=None)
    ticks = []
    for off in range(-TL_PAST, TL_FUTURE + 1):
        day = today + dt.timedelta(days=off)
        if day.weekday() == 0 and (x(off) + 50 < x(0) or x(off) > x(0) + 22) and x(off) < W - 18:   # подпись не наезжает на «сегодня»
            ticks.append(f'<line x1="{x(off):.1f}" x2="{x(off):.1f}" y1="12" y2="{H}" stroke="{GRID}"/>'
                         f'<text x="{x(off) + 2:.1f}" y="9" class="ax">{dm(day)}</text>')
    head = (f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="none" class="tls">{"".join(ticks)}'
            f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="11" y2="{H}" stroke="{INK}" stroke-width="1.2"/>'
            f'<text x="{x(0):.1f}" y="9" text-anchor="middle" class="axb">сегодня</text></svg>')
    out = [f'<div class="tlr tlh"><span></span><span></span><span>исполнитель</span><span>статус</span><div class="tlc">{head}</div><span class="r">отклонение</span></div>']
    grid = "".join(f'<line x1="{x(off):.1f}" x2="{x(off):.1f}" y1="0" y2="{H}" stroke="{GRID}"/>'
                   for off in range(-TL_PAST, TL_FUTURE + 1) if (today + dt.timedelta(days=off)).weekday() == 0)
    for r in rows:
        g = [grid, f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="0" y2="{H}" stroke="{INK}" stroke-width="1.2"/>']
        cy, left = H / 2, r["left"]
        shape = (lambda cx, fill, stroke: f'<circle cx="{cx:.1f}" cy="{cy}" r="3.6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>') if r["kind"] == "epic" else \
                (lambda cx, fill, stroke: f'<path d="M{cx:.1f},{cy - 4.4} L{cx + 4.4:.1f},{cy} L{cx:.1f},{cy + 4.4} L{cx - 4.4:.1f},{cy} Z" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        if left is not None and left < 0:
            cx = max(x(left), 5)
            g.append(f'<rect x="{cx:.1f}" y="{cy - 2.5}" width="{x(0) - cx:.1f}" height="5" fill="{RED}" opacity=".85"/>' + shape(cx, RED, RED))
        elif left == 0:
            g.append(shape(x(0), AMBER, AMBER))
        elif left is not None:
            g.append(shape(min(x(left), W - 6), "#fff", INK))
        key = r["key"] or r["id"]
        href = link(m, key) if r["key"] else "#"
        out.append(f'<a class="tlr" href="{href}"><span class="tk">{e(key)}</span><span class="tt">{e(clean(r["what"]))}</span>'
                   f'<span class="tw">{e(surname(r["who"])) or "—"}</span><span class="ts">{state(r)}</span>'
                   f'<div class="tlc"><svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="none">{"".join(g)}</svg></div>'
                   f'{deviation(left, worst)}</a>')
    more = len(m["dates"]) - TOP_DATES
    return '<div class="tl">' + "".join(out) + "</div>" + (f'<div class="note">+{more} ещё</div>' if more > 0 else "")


def epics(m):
    """Все эпики в работе карточками: % готовности, полоса (зелёным — закрыто за 2 недели, красным — в блоке),
    квадраты — истории этого спринта."""
    eps = [x for x in m["t"]["epics"] if x.get("key") and (x["work"] or x["sprint"]["work"] or x["sprint"]["todo"])]
    eps.sort(key=lambda x: (-(x.get("d14n") or 0), -x["work"]))
    if not eps:
        return '<div class="empty">Эпиков в работе нет</div>'
    cards = []
    for x in eps:
        c, sp = x["cats"], x["sprint"]
        tot = max(1, sum(c.values()))
        d14 = min(x.get("d14n") or 0, c["done"])
        blk = min(x.get("blocked") or 0, c["work"] + c["todo"])   # блок — из «в работе», остаток из «не начато»
        segs = ((c["done"] - d14, DONE), (d14, OK), (max(0, c["work"] - blk), WIP), (blk, RED))
        bar = "".join(f'<i style="width:{n / tot * 100:.1f}%;background:{col}"></i>' for n, col in segs if n > 0)
        move = f'<span class="em">+{d14} за 2 нед</span>' if d14 else '<span class="em stop">стоит 2 нед</span>'
        n = sum(sp.values())
        sq = "".join(f'<i class="{k}"></i>' for k in ("done", "work", "todo") for _ in range(sp.get(k, 0)))
        spr = f'<div class="es"><span>спринт</span><span class="sq">{sq}</span><span>{sp["done"]}/{n}</span></div>' if n else ""
        hold = f'<span class="eh">{blk} в блоке</span>' if blk else ""
        cards.append(f"""<a class="ec" href="{link(m, x['key'])}"><div class="ep">{x['pct']}<small>%</small></div>
<div class="eb"><div class="et">{e(clean(x['title']))}</div><div class="ebar">{bar}</div><div class="ef">{spr}<span class="er">{hold}{move}</span></div></div></a>""")
    return '<div class="epics">' + "".join(cards) + "</div>"


def block(title, body, aside=""):
    return f'<section><div class="bh"><h2>{title}</h2>{aside}</div>{body}</section>'


def lg(items):
    return '<span class="lg">' + "".join(f'<span><i style="background:{c}"></i>{e(t)}</span>' for c, t in items) + "</span>"


def page1(m, team):
    t, s = m["t"], m["s"]
    return f"""<div class="page"><main class="inner">
{header(m, team, f"Спринт {e(t['sprint'])} · {dm(s['start'])}–{dm(s['end'])}", "1")}
{kpis(m)}
{sprint_block(m)}
{block("Сроки и обещания", timeline(m), '<span class="lg"><span>● эпик</span><span>◆ обещание</span></span>')}
{block("Эпики в спринте", epics(m), lg([(DONE, "готово"), (OK, "закрыто за 2 нед"), (WIP, "в работе"), (RED, "в блоке")]))}
<footer><span>Отчёт спринта · {e(team)} · дни рабочие</span><span>1 / 2</span></footer>
</main></div>"""


# ---------- стр. 2 ----------

def team_strip(m):
    nbs = {p["short"]: sum(1 for b in m["blocked"] if b["who"] == p["short"]) for p in m["t"]["people"]}
    ps = sorted(m["t"]["people"], key=lambda p: (-nbs[p["short"]], -p["split"]["work"], p["short"]))
    cells = []
    for p in ps:
        sp = p["split"]
        tot = max(1, sum(sp.values()))
        bar = "".join(f'<i style="width:{sp[k] / tot * 100:.1f}%;background:{c}"></i>'
                      for k, c in (("done", DONE), ("work", WIP), ("blocked", RED), ("open", TODO)) if sp.get(k))
        nb = nbs[p["short"]]
        cells.append(f"""<div class="pc"><span class="av">{e(p['initials'])}</span><span class="pn">{e(surname(p['short']))}
{f'<em>{nb} блок</em>' if nb else ''}</span><span class="pb">{bar}</span></div>""")
    return f'<div class="strip">{"".join(cells)}</div>'


def card(m, x, kind):
    days = x.get("days") or 0
    cls, dcls = "", ""
    if kind == "block":
        cls, dcls = ("blk hot" if days >= 10 else "blk"), ("dred" if days >= 10 else "")
    elif days > STALE_DAYS:
        cls, dcls = "stl", "damb"
    rl = role(x["title"])
    reason = ""
    if kind == "block":
        reason = f'<div class="cr">↳ {e(x.get("reason"))}</div>' if x.get("reason") else '<div class="cr muted">↳ без комментария</div>'
    ini = "".join(w[0] for w in str(x.get("who") or "").replace(".", " ").split()[:2]).upper()
    return f"""<a class="card {cls}" href="{link(m, x['key'])}"><div class="c1"><span class="ck">{e(x['key'])}{f' · {rl}' if rl else ''}</span>
<span class="cd {dcls}">{days} дн</span><span class="ci">{e(ini)}</span></div><div class="ct">{e(clean(x['title']))}</div>{reason}</a>"""


def done_card(m, x):
    at = dt.datetime.fromisoformat(x["at"])
    day = at.date()
    when = ("сегодня" if day == m["today"] else "вчера" if day == m["today"] - dt.timedelta(days=1) else WD[day.weekday()]) + f" {at:%H:%M}"
    return f"""<a class="card dn" href="{link(m, x['key'])}"><div class="c1"><span class="ck">{e(x['key'])}</span><span class="cd">{when}</span></div>
<div class="ct one">{e(clean(x['title']))}</div></a>"""


def page2(model, m, team):
    cols = [("В блоке", RED, [card(m, b, "block") for b in m["blocked"]], CARD_LIMIT, "wide")]
    for title, bucket in (("В работе", "progress"), ("Ревью", "review"), ("Отладка", "testing")):
        xs = sorted([x for x in m["tasks"] if x.get("bucket") == bucket], key=lambda x: -(x["days"] or 0))
        cols.append((title, "#D5D8DE", [card(m, x, "task") for x in xs], CARD_LIMIT, ""))
    done = sorted([x for x in uniq(model["done"], "key") if x["team"] == team], key=lambda x: x["at"], reverse=True)
    cols.append(("Готово", OK, [done_card(m, x) for x in done], DONE_LIMIT, ""))
    html_cols = []
    for title, color, cards, limit, cls in cols:
        more = f'<div class="more">+{len(cards) - limit} ещё</div>' if len(cards) > limit else ""
        body = "".join(cards[:limit]) or '<div class="none">—</div>'
        html_cols.append(f'<div class="col {cls}"><div class="colh" style="border-color:{color}">{title}<span> {len(cards)}</span></div>{body}{more}</div>')
    return f"""<div class="page"><main class="inner">
{header(m, team, "доска", "2")}
<div class="kb-lg">{lg([(RED, "блок"), (AMBER, f"застой >{STALE_DAYS} дн")])}</div>
{team_strip(m)}
{block("Стоит дольше всего", longest(m), lg([(RED, "блок"), (AMBER, "без движения")]))}
<div class="board">{"".join(html_cols)}</div>
<footer><span>Отчёт спринта · {e(team)} · дни рабочие</span><span>2 / 2</span></footer>
</main></div>"""


def render(model, ops, team):
    m = summary(model, ops, team)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Отчёт спринта {e(team)} {dm(m['today'])}</title>
<style>{CSS}</style></head><body>{page1(m, team)}{page2(model, m, team)}<script>{FIT}</script></body></html>"""


# страховка: если контент страницы выше листа — уменьшить масштаб этой страницы, а не потерять низ
FIT = """document.querySelectorAll('.page').forEach(function(p){var i=p.querySelector('.inner'),max=p.clientHeight,k=1;
i.style.minHeight='0';while(i.getBoundingClientRect().height>max&&k>0.6){k-=0.01;i.style.zoom=k;}
i.style.minHeight=(max/k-1)+'px';});"""

CSS = f"""
@page {{ size: A4 portrait; margin: 12mm 12mm 10mm; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; color: {INK}; font: 400 8.5pt/1.3 Inter, system-ui, sans-serif; font-feature-settings: "tnum";
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
a {{ color: inherit; text-decoration: none; }}
.page {{ height: 275mm; overflow: hidden; break-after: page; }} .page:last-of-type {{ break-after: auto; }}
.inner {{ min-height: 275mm; display: flex; flex-direction: column; gap: 6mm; }}
.muted {{ color: {MUTED}; font-size: 7pt; }} .amber {{ color: {AMBER}; font-weight: 600; }}
h2 {{ margin: 0; font-size: 11pt; font-weight: 600; line-height: 1.25; }}
.bh {{ display: flex; align-items: baseline; justify-content: space-between; gap: 4mm; margin-bottom: 2.5mm; }}
.lg {{ display: inline-flex; gap: 3mm; font-size: 7pt; color: {MUTED}; }}
.lg i {{ display: inline-block; width: 3mm; height: 1.2mm; border-radius: .6mm; margin-right: 1.2mm; vertical-align: .5mm; }}
.empty {{ color: {MUTED}; font-size: 8.5pt; padding: 2mm 0; }}
.note {{ margin-top: 1.5mm; color: {MUTED}; font-size: 7pt; }}

.hd {{ display: flex; justify-content: space-between; align-items: baseline; }}
.team {{ font-size: 22pt; font-weight: 700; line-height: 1; letter-spacing: -.01em; }}
.sub {{ margin-left: 3mm; color: {SEC}; font-size: 8.5pt; }}
.when {{ color: {MUTED}; font-size: 7pt; }}

.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 4mm; border-top: .75pt solid {INK}; padding-top: 2.5mm; }}
.kl {{ font-size: 7pt; font-weight: 500; color: {SEC}; }}
.kv {{ margin: 1mm 0 1.6mm; font-size: 22pt; font-weight: 600; line-height: 1; }}
.kv span {{ font-size: 8.5pt; font-weight: 400; color: {MUTED}; }}
.ks {{ margin-top: 1.3mm; font-size: 7pt; color: {MUTED}; }}
.seg {{ display: flex; gap: .5mm; height: 2.5mm; }} .seg i {{ border-radius: .4mm; }}
.pace {{ position: relative; height: 2.5mm; background: {TODO}; border-radius: .4mm; overflow: visible; }}
.pace i {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: .4mm 0 0 .4mm; }}
.pace i.hatch {{ background: repeating-linear-gradient(45deg, {RED} 0 .5pt, transparent .5pt 3pt); border-radius: 0; }}
.pace b {{ position: absolute; top: -.8mm; bottom: -.8mm; width: 1pt; background: {INK}; }}
.kz {{ position: relative; height: 11mm; display: flex; flex-direction: column; justify-content: flex-end; }}
.ln {{ position: absolute; right: 0; transform: translateY(-.4mm); font-size: 6.5pt; font-weight: 600; color: {RED}; background: #fff; padding-left: .8mm; }}
.spk {{ display: block; height: 11mm; }}
.fbar {{ position: relative; height: 3mm; background: {TODO}; border-radius: .5mm; display: flex; }} .fbar i {{ display: block; height: 100%; }}
.fbar i.hatch-b {{ background: repeating-linear-gradient(45deg, {DONE} 0 .7pt, {WIP} .7pt 3pt); }}
.fbar b {{ position: absolute; top: -1mm; bottom: -1mm; width: 1.2pt; background: {INK}; }}
.wait {{ justify-content: flex-end; gap: 0; }}
.wr {{ display: grid; grid-template-columns: 11mm 1fr; align-items: center; column-gap: 1mm; height: 2.7mm; font-size: 6.5pt; line-height: 1; color: {MUTED}; }}
.wr i {{ display: block; height: 1.8mm; border-radius: .4mm; min-width: .6mm; }} .wr .hot {{ color: {RED}; font-weight: 600; }}
.dl {{ margin-left: 2mm; font-size: 7pt; font-weight: 600; color: {MUTED}; }} .dl.ok {{ color: {OK}; }} .dl.bad {{ color: {RED}; }}
.dots {{ display: flex; flex-wrap: wrap; gap: .7mm; min-height: 2.5mm; align-items: center; }}
.dots i {{ width: 1.6mm; height: 1.6mm; border-radius: 50%; }}

.long {{ display: flex; flex-direction: column; }}
.lrow {{ display: grid; grid-template-columns: 82mm 20mm 1fr; column-gap: 3mm; align-items: center; height: 5mm; }}
.lt {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.lw {{ font-size: 7pt; color: {MUTED}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.lb {{ display: flex; align-items: center; gap: 1.5mm; }}
.lb i {{ display: block; height: 2.4mm; border-radius: .4mm; min-width: 1mm; }}
.lb em {{ font-style: normal; font-size: 7pt; color: {SEC}; white-space: nowrap; }} .lb em.hot {{ font-size: 8.5pt; font-weight: 600; }}

.row2 {{ display: grid; grid-template-columns: 92mm 1fr; gap: 6mm; align-items: start; }}
.verdict {{ font-size: 8.5pt; color: {SEC}; }} .verdict b.red {{ color: {RED}; font-weight: 600; }}
.pace-l {{ font-size: 7pt; color: {SEC}; margin-top: 1mm; }} .pace-l b {{ color: {INK}; font-weight: 600; }} .pace-l.muted {{ color: {MUTED}; }}
.dec {{ display: flex; flex-direction: column; gap: 2.4mm; }}
.dr {{ border-left: 1.2mm solid; padding-left: 2.5mm; }}
.dt {{ display: flex; align-items: baseline; gap: 2mm; }}
.dt b {{ font-size: 11pt; font-weight: 600; }} .dt span {{ font-size: 7pt; color: {MUTED}; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 1mm; margin-top: 1.2mm; }}
.chip {{ font-size: 7pt; line-height: 1; padding: .9mm 1.4mm; border-radius: .8mm; background: {SURF}; color: {INK}; }}
.chip.more {{ background: none; color: {MUTED}; }}
svg .ax {{ font: 400 7pt Inter, sans-serif; fill: {MUTED}; }}
svg .axb {{ font: 600 7pt Inter, sans-serif; fill: {INK}; }}
svg .axr {{ font: 600 7pt Inter, sans-serif; fill: {RED}; }}
svg .val {{ font: 600 11pt Inter, sans-serif; fill: {INK}; }}
svg .gap {{ font: 600 8.5pt Inter, sans-serif; fill: {RED}; }}

.tl {{ display: flex; flex-direction: column; }}
.tlr {{ display: grid; grid-template-columns: 19mm 1fr 18mm 22mm 40mm 16mm; column-gap: 2.5mm; align-items: center; height: 4.8mm; }}
.tlr.tlh {{ font-size: 7pt; color: {MUTED}; }} .tlr .r {{ text-align: right; }}
.tk {{ font-size: 7pt; color: {MUTED}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tt {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tw {{ font-size: 7pt; color: {SEC}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.ts {{ display: flex; align-items: center; gap: 1.2mm; font-size: 7pt; color: {SEC}; white-space: nowrap; overflow: hidden; }}
.sb {{ display: flex; flex: none; width: 9mm; height: 1.8mm; background: {TODO}; border-radius: .4mm; overflow: hidden; }} .sb i {{ display: block; }}
.tlc svg {{ display: block; height: 4.8mm; }}
.dv {{ font-size: 7pt; color: {MUTED}; text-align: right; white-space: nowrap; }} .dv.red {{ color: {RED}; }} .dv.hot {{ font-weight: 600; }}
.dv.amber {{ color: {AMBER}; font-weight: 600; }}

.epics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 3.5mm 7mm; }}
.ec {{ display: grid; grid-template-columns: 14mm 1fr; column-gap: 2.5mm; align-items: start; min-width: 0; }}
.ep {{ font-size: 22pt; font-weight: 600; line-height: .9; letter-spacing: -.02em; }} .ep small {{ font-size: 8.5pt; font-weight: 400; color: {MUTED}; }}
.eb {{ min-width: 0; }}
.et {{ font-size: 8.5pt; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.ebar {{ display: flex; height: 2.6mm; margin-top: 1.2mm; background: {TODO}; border-radius: .5mm; overflow: hidden; }} .ebar i {{ display: block; }}
.ef {{ display: flex; justify-content: space-between; align-items: center; margin-top: 1.2mm; font-size: 7pt; color: {MUTED}; }}
.er {{ display: flex; gap: 2.5mm; margin-left: auto; }} .eh {{ color: {RED}; font-weight: 600; white-space: nowrap; }}
.em {{ color: {OK}; font-weight: 600; white-space: nowrap; }} .em.stop {{ color: {AMBER}; }}
.es {{ display: flex; align-items: center; gap: 1.2mm; }}
.sq {{ display: flex; gap: .5mm; }} .sq i {{ width: 1.6mm; height: 1.6mm; border-radius: .3mm; }}
.sq i.done {{ background: {DONE}; }} .sq i.work {{ background: {WIP}; }} .sq i.todo {{ background: #fff; box-shadow: inset 0 0 0 .5pt {MUTED}; }}

footer {{ margin-top: auto; display: flex; justify-content: space-between; font-size: 7pt; color: {MUTED}; }}

.kb-lg {{ margin-top: -4mm; text-align: right; }}
.strip {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 2.5mm 4mm; }}
.pc {{ display: grid; grid-template-columns: 6mm 1fr; grid-template-rows: auto 1.5mm; column-gap: 1.5mm; row-gap: 1mm; align-items: center; min-width: 0; }}
.av {{ grid-row: 1 / 3; width: 6mm; height: 6mm; border-radius: 50%; background: {SURF}; display: grid; place-items: center; font-size: 7pt; font-weight: 600; }}
.pn {{ font-size: 7pt; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }} .pn em {{ font-style: normal; color: {RED}; margin-left: 1mm; }}
.pb {{ display: flex; height: 1.5mm; border-radius: .4mm; overflow: hidden; background: {TODO}; }} .pb i {{ display: block; }}
.board {{ flex: 1; display: grid; grid-template-columns: 42mm repeat(4, minmax(0, 1fr)); gap: 3mm; align-items: start; }}
.colh {{ font-size: 8.5pt; font-weight: 600; padding-bottom: 1.2mm; border-bottom: 2pt solid; margin-bottom: 2mm; }}
.colh span {{ color: {MUTED}; font-weight: 400; }}
.card {{ display: block; border: .5pt solid {LINE}; border-radius: 1.5mm; padding: 1.6mm 1.8mm; margin-bottom: 1.6mm; background: #fff; }}
.card.blk {{ border-left: 2pt solid {RED}; }} .card.blk.hot {{ border-left-width: 3pt; }} .card.stl {{ border-left: 2pt solid {AMBER}; }}
.c1 {{ display: flex; align-items: center; gap: 1mm; font-size: 7pt; color: {MUTED}; }}
.ck {{ flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.cd {{ white-space: nowrap; }} .cd.dred {{ color: {RED}; font-weight: 600; font-size: 8.5pt; }} .cd.damb {{ color: {AMBER}; font-weight: 600; }}
.ci {{ width: 4.5mm; height: 4.5mm; border-radius: 50%; background: {SURF}; display: grid; place-items: center; font-size: 6pt; font-weight: 600; color: {INK}; flex: none; }}
.ct {{ margin-top: .8mm; font-size: 7pt; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.ct.one {{ -webkit-line-clamp: 1; }}
.cr {{ margin-top: .8mm; font-size: 7pt; color: {SEC}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }} .cr.muted {{ color: {MUTED}; }}
.card.dn {{ padding: 1.2mm 1.8mm; }}
.more, .none {{ text-align: center; font-size: 7pt; color: {MUTED}; padding: 1mm 0; }}
"""
