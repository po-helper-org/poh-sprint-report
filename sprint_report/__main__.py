"""Командная строка.

  python -m sprint_report demo   [--out DIR] [--day ГГГГ-ММ-ДД] [--html-only]   отчёт на вымышленных данных, без Jira
  python -m sprint_report collect -c config.json [--team SLUG] [--record DIR | --replay DIR]   снимки из Jira
  python -m sprint_report report  -c config.json [--day …] [--snapshots DIR] [--html-only]    PDF из снимков
  python -m sprint_report run     -c config.json [--day …] [--send]                            сбор + PDF (+ отправка)
  python -m sprint_report observe --data sprint-report.data.json --team SLUG [--day …]          HTML для экрана из снимка PO-Sprint-observe
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from . import config as C
from . import demo, deliver, metrics, observe, pdf, render
from .collect import Collector
from .jira import Jira, JiraError


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def state_dir(cfg, day):
    return C.path(cfg, cfg.get("state_dir"), "~/.local/state/sprint-report") / day.isoformat()


def build_report(snaps, day, out, promises=None, chrome=None, html_only=False):
    """Снимки → data.json, HTML и PDF на каждую команду в каталоге out. Возвращает пути PDF (или HTML)."""
    out.mkdir(parents=True, exist_ok=True)
    model, ops = metrics.build(snaps, day, promises)
    (out / "data.json").write_text(json.dumps({"model": model, "ops": ops}, ensure_ascii=False), encoding="utf-8")
    browser = None if html_only else pdf.find_chrome(chrome)
    paths = []
    for team in render.teams(ops):
        stem = out / f"{re.sub(r'[^0-9A-Za-zА-Яа-яЁё_-]+', '_', team)}-{day.isoformat()}"
        stem.with_suffix(".html").write_text(pdf.with_fonts(render.render(model, ops, team)), encoding="utf-8")
        if html_only:
            paths.append(stem.with_suffix(".html"))
            continue
        pdf.print_pdf(stem.with_suffix(".html"), stem.with_suffix(".pdf"), browser, out.parent / ".chrome-profile")
        paths.append(stem.with_suffix(".pdf"))
    return paths, model, ops


def jira_client(cfg, record=None, replay=None):
    j = cfg["jira"]
    token = C.read_secret(j, "JIRA_TOKEN")
    if not token and not replay:
        raise SystemExit("нет токена Jira: переменная из jira.token_env (по умолчанию JIRA_TOKEN) или jira.token_file")
    user = j.get("user") or (os.environ.get(j["user_env"]) if j.get("user_env") else None)
    return Jira(j["url"], token or "-", user=user, ca_bundle=j.get("ca_bundle"), record=record, replay=replay)


def collect(cfg, day, team=None, record=None, replay=None):
    tz = C.tz(cfg)
    jira = jira_client(cfg, record, replay)
    folder = state_dir(cfg, day) / "snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    snaps = []
    for t in cfg["teams"]:
        if team and t["slug"] != team:
            continue
        snap = Collector(jira, t, tz).collect()
        (folder / f"{t['slug']}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        log(f"{t['slug']}: спринт «{snap['sprint']['name']}», задач {len(snap['issues'])}, эпиков {len(snap['epics'])}")
        snaps.append(snap)
    log(f"запросов к Jira: {jira.requests}")
    return snaps


def load_snapshots(folder):
    files = sorted(Path(folder).glob("*.json"))
    if not files:
        raise SystemExit(f"нет снимков в {folder}: сначала collect")
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def load_promises(cfg):
    p = cfg.get("promises_file")
    return json.loads(C.path(cfg, p, "").read_text(encoding="utf-8")) if p else None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sprint_report", description="PDF-отчёт команды по спринту из Jira")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("demo", "collect", "report", "run"):
        p = sub.add_parser(name)
        p.add_argument("--day", help="ГГГГ-ММ-ДД, по умолчанию сегодня")
        if name != "demo":
            p.add_argument("-c", "--config", required=True)
        if name in ("demo", "report", "run"):
            p.add_argument("--html-only", action="store_true", help="без печати PDF")
        if name == "demo":
            p.add_argument("--out", default="demo-out")
        if name == "collect":
            p.add_argument("--team")
            g = p.add_mutually_exclusive_group()
            g.add_argument("--record", help="сохранить ответы Jira в каталог")
            g.add_argument("--replay", help="работать из сохранённых ответов, без сети")
        if name == "report":
            p.add_argument("--snapshots", help="каталог снимков, по умолчанию <state_dir>/<день>/snapshots")
        if name == "run":
            p.add_argument("--send", action="store_true", help="отправить по разделу deliver конфига")
    p = sub.add_parser("observe", help="HTML команды для экрана из снимка PO-Sprint-observe (без Jira и Chrome)")
    p.add_argument("--data", required=True, help="sprint-report.data.json виджета PO-Sprint-observe")
    p.add_argument("--team", required=True, help="slug команды")
    p.add_argument("--day", help="ГГГГ-ММ-ДД, по умолчанию сегодня")
    p.add_argument("--promises", help="JSON обещаний (как promises_file)")
    a = ap.parse_args(argv)

    if a.cmd == "observe":
        day = dt.date.fromisoformat(a.day) if a.day else dt.date.today()
        snaps = observe.snapshots(json.loads(Path(a.data).read_text(encoding="utf-8")), a.team)
        if not snaps:
            log(f"в снимке нет команды {a.team} со спринтом")
            return 2
        promises = json.loads(Path(a.promises).read_text(encoding="utf-8")) if a.promises else {}
        model, ops = metrics.build(snaps, day, promises)
        name = snaps[0]["team"]["name"]
        sys.stdout.write(observe.web(pdf.with_fonts(render.render(model, ops, name))))
        return 0


    if a.cmd == "demo":
        day = dt.date.fromisoformat(a.day) if a.day else dt.date.today()
        paths, _, _ = build_report([demo.snapshot(day)], day, Path(a.out), demo.promises(day), html_only=a.html_only)
        print("\n".join(map(str, paths)))
        return 0

    cfg = C.load(a.config)
    day = dt.date.fromisoformat(a.day) if a.day else dt.datetime.now(C.tz(cfg)).date()
    chrome = (cfg.get("pdf") or {}).get("chrome")
    try:
        if a.cmd == "collect":
            collect(cfg, day, a.team, a.record, a.replay)
            return 0
        snaps = collect(cfg, day) if a.cmd == "run" else load_snapshots(a.snapshots or state_dir(cfg, day) / "snapshots")
    except JiraError as exc:
        log(f"Jira: {exc}")
        return 3
    paths, model, ops = build_report(snaps, day, state_dir(cfg, day), load_promises(cfg), chrome, a.html_only)
    print("\n".join(map(str, paths)))
    if a.cmd == "run" and a.send:
        how = deliver.deliver(cfg, paths, deliver.caption(model, ops, day))
        log(f"отправлено: {how}" if how else "раздела deliver в конфиге нет — отчёт остался файлами")
    return 0


if __name__ == "__main__":
    sys.exit(main())
