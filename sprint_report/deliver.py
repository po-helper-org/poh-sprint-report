"""Отправка отчёта: подпись по командам и PDF-файлы в комнату Matrix (Element). Необязательно — без раздела
deliver в конфиге отчёт просто остаётся файлами.

Токен — уже выданный access token бота (env или файл). Нового входа здесь нет намеренно: он создал бы
ещё одну сессию и мог бы выбить сессию работающего бота.
"""
import html
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import render
from .config import read_secret

BLOCK_BINS = [(10, None, "D10+"), (5, 10, "D5+"), (3, 5, "D3+")]   # раб. дней в блоке: [10;∞), [5;10), [3;5)
FLOW_ROWS = [("work", "Взято в работу"), ("review", "Передано в ревью"), ("testing", "Передано в отладку"), ("done", "Выполнено")]


def caption(model, ops, day):
    """По блоку на команду: блоки по давности и переходы за сутки / 2–3 сутки."""
    lines = [f"📄 Отчёт спринта {render.WD[day.weekday()]} {day:%d.%m}"]
    for team in render.teams(ops):
        m = render.summary(model, ops, team)
        days = [b["days"] or 0 for b in m["blocked"]]
        bins = " / ".join(f"{lbl} {sum(1 for x in days if x >= lo and (hi is None or x < hi))}" for lo, hi, lbl in BLOCK_BINS)
        fl = m["t"].get("flow") or {}
        lines += ["", f"{team}:", f"Заблокировано: {bins}"]
        lines += [f"{title}: D1- {fl.get(k, [0, 0])[0]} / D-3 {fl.get(k, [0, 0])[1]}" for k, title in FLOW_ROWS]
    return "\n".join(lines)


class Matrix:
    def __init__(self, homeserver, token):
        self.hs = homeserver.rstrip("/")
        self.token = token

    def _call(self, method, path, body=None, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.hs + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)

    def send(self, room, content):
        txn = f"sr{time.time_ns()}"
        return self._call("PUT", f"/_matrix/client/v3/rooms/{urllib.parse.quote(room)}/send/m.room.message/{txn}", content)

    def upload(self, data, mime, name):
        return self._call("POST", f"/_matrix/media/v3/upload?filename={urllib.parse.quote(name)}", data, mime)["content_uri"]


def send_matrix(cfg, paths, text):
    token = read_secret(cfg, "MATRIX_TOKEN")
    if not token:
        raise RuntimeError("нет токена Matrix: deliver.matrix.token_env или token_file")
    mx = Matrix(cfg["homeserver"], token)
    mx._call("GET", "/_matrix/client/v3/account/whoami")   # токен жив — иначе падаем до отправки половины
    room = cfg["room_id"]
    mx.send(room, {"msgtype": "m.text", "body": text, "format": "org.matrix.custom.html",
                   "formatted_body": html.escape(text).replace("\n", "<br>")})
    for p in paths:
        data = Path(p).read_bytes()
        name = Path(p).name
        url = mx.upload(data, "application/pdf", name)
        mx.send(room, {"msgtype": "m.file", "body": name, "url": url, "info": {"mimetype": "application/pdf", "size": len(data)}})


def deliver(cfg, paths, text):
    if (cfg.get("deliver") or {}).get("matrix"):
        send_matrix(cfg["deliver"]["matrix"], paths, text)
        return "matrix"
    return None

