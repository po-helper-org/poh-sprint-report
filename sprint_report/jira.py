"""Клиент Jira только на чтение: GET, проверка TLS, постраничный обход, запись и воспроизведение ответов.

Авторизация: Bearer (Personal Access Token Jira Server/DC) или Basic (почта + API-токен Jira Cloud).
Токен в дамп ответов не попадает никогда: пишутся только путь, параметры и тело.
"""
import base64
import hashlib
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class JiraError(Exception):
    """Jira недоступна, не авторизует или ответила ошибкой."""


class Jira:
    def __init__(self, base, token, user=None, ca_bundle=None, record=None, replay=None, timeout=120):
        self.base = base.rstrip("/")
        self.auth = ("Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()) if user else ("Bearer " + str(token))
        self.timeout = timeout
        self.requests = 0
        self.record = Path(record) if record else None
        self.replay = Path(replay) if replay else None
        if self.record:
            self.record.mkdir(parents=True, exist_ok=True)
        try:   # проверка сертификата включена всегда; корпоративный CA — через ca_bundle
            self.ctx = ssl.create_default_context(cafile=str(ca_bundle) if ca_bundle else None)
        except OSError as exc:
            raise JiraError(f"не читается CA-бандл {ca_bundle}: {exc.strerror}") from exc

    @staticmethod
    def _key(path, params):
        canon = path + "?" + urllib.parse.urlencode(sorted(params.items()))
        return hashlib.sha1(canon.encode()).hexdigest()[:16], canon

    def get(self, path, **params):
        key, canon = self._key(path, params)
        self.requests += 1
        if self.replay:
            f = self.replay / f"{key}.json"
            if not f.is_file():
                raise JiraError(f"в replay-каталоге нет ответа на GET {canon} ({f.name})")
            return json.loads(f.read_text(encoding="utf-8"))
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"Authorization": self.auth, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise JiraError(f"Jira не авторизует запрос (HTTP {exc.code}) — проверьте токен") from exc
            raise JiraError(f"Jira вернула HTTP {exc.code} на GET {canon}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise JiraError(f"сертификат Jira не проверился ({exc.reason}); корпоративный CA — в jira.ca_bundle") from exc
            raise JiraError(f"Jira недоступна ({exc.reason}) — проверьте VPN и адрес") from exc
        if self.record:
            (self.record / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            index = self.record / "_index.json"
            known = json.loads(index.read_text(encoding="utf-8")) if index.is_file() else {}
            known[key] = canon
            index.write_text(json.dumps(known, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        return data

    def values(self, path, **params):
        """Агильные списки (спринты доски): обход всех страниц — первая отдаёт самые старые записи."""
        out, start = [], 0
        while True:
            d = self.get(path, startAt=start, maxResults=50, **params)
            vals = d.get("values", [])
            out += vals
            start += len(vals)
            if d.get("isLast", True) or not vals:
                return out

    def issues(self, path, **params):
        """Задачи спринта или поиска JQL: обход по total."""
        out, start = [], 0
        while True:
            d = self.get(path, startAt=start, maxResults=100, **params)
            batch = d.get("issues", [])
            out += batch
            start += len(batch)
            if start >= d.get("total", 0) or not batch:
                return out
