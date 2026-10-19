"""Демо-снимок: вымышленная команда «Альфа» — люди, задачи и эпики выдуманы, ключи ALF-*.

Нужен, чтобы посмотреть отчёт без Jira, для тестов и для публичных иллюстраций (реальные данные наружу не идут).
Генерация детерминирована: один и тот же день → один и тот же снимок.
"""
import datetime as dt
import random

PEOPLE = ["Белова Мария", "Громов Кирилл", "Демидов Олег", "Жукова Ксения", "Зайцев Артём",
          "Исаева Полина", "Котов Денис", "Лебедев Иван"]
STATUS = {"open": "Открыто", "progress": "В работе", "review": "Код-ревью", "testing": "Тестирование",
          "blocked": "В ожидании", "done": "Готово"}
EPICS = [("Оплата в один клик", -12), ("Личный кабинет: история заказов", -5), ("Переезд каталога на PostgreSQL", 0),
         ("Уведомления о статусе заказа", 6), ("Промокоды для партнёров", 12), ("Мониторинг доставки вебхуков", 30)]
TASKS = [
    "[BE] API списания по сохранённой карте", "[FE] Кнопка «Оплатить в один клик»", "[QA] Регресс оплаты картой",
    "[BE] Хранение токена карты", "[SA] Сценарии отказа банка", "[FE] История заказов: фильтры",
    "[BE] История заказов: пагинация", "[QA] Автотесты личного кабинета", "[BE] Миграция справочника площадок",
    "[BE] Миграция расписания сеансов", "[DEVOPS] Реплика PostgreSQL для отчётов", "[QA] Сверка данных после переезда",
    "[BE] Очередь уведомлений", "[FE] Настройки уведомлений в профиле", "[SA] Тексты уведомлений",
    "[BE] Генерация промокодов", "[FE] Ввод промокода в корзине", "[BE] Лимиты промокодов партнёра",
    "[BE] Повторная доставка вебхуков", "[DEVOPS] Алерты на ошибки доставки", "[FE] Статус заказа на главной",
    "[BE] Отмена заказа из кабинета", "[QA] Нагрузочный тест оплаты", "[SA] Описание статусов заказа",
    "[BE] Возвраты по частичной оплате", "[FE] Экран ошибки оплаты", "[BE] Журнал действий оператора",
    "[QA] Проверка вебхуков партнёра", "[FE] Карточка промокода", "[BE] Кэш каталога",
]
REASONS = ["Ждём доступы к стенду от DevOps", "Ждём ответ партнёра по контракту API",
           "Нужно решение по макету от дизайна", "Ждём ревью безопасности", "Банк не подтвердил тестовые карты"]


def workdays_back(d, n):
    while n > 0:
        d -= dt.timedelta(days=1)
        n -= d.weekday() < 5
    return d


def stamp(d, hour, minute=0):
    return dt.datetime.combine(d, dt.time(hour, minute)).isoformat()[:16]


def snapshot(day=None, seed=7):
    day = day or dt.date.today()
    rnd = random.Random(f"{seed}-{day.isoformat()}")
    start = workdays_back(day, 7)
    end = start + dt.timedelta(days=13)
    collected = dt.datetime.combine(day, dt.time(8, 30))
    ago = lambda n: workdays_back(day, n)   # noqa: E731
    epic_keys = [f"ALF-{100 + n}" for n in range(len(EPICS))]
    issues = []
    # итоговая колонка задачи и сколько рабочих дней она в ней: задаёт картину спринта
    plan = (["done"] * 9 + ["testing"] * 2 + ["review"] * 4 + ["progress"] * 6 + ["blocked"] * 4 + ["open"] * 5)
    blocked_days = [12, 7, 4, 2]
    for n, title in enumerate(TASKS):
        key = f"ALF-{200 + n}"
        final = plan[n % len(plan)]
        who = PEOPLE[(n * 3) % len(PEOPLE)] if not (final == "open" and n % 3 == 0) else ""
        sp = rnd.choice([1, 2, 3, 3, 5, 5, 8]) if n % 11 else rnd.choice([0, 13])
        added = n in (5, 13, 21, 27)                     # пришли в спринт после старта
        entered = stamp(ago(rnd.randint(2, 5)), 11) if added else None
        created = stamp(start - dt.timedelta(days=rnd.randint(3, 20)), 10)
        hist, t = [], max(start, dt.date.fromisoformat(entered[:10])) if entered else start
        path = {"open": [], "progress": ["progress"], "review": ["progress", "review"],
                "testing": ["progress", "review", "testing"], "blocked": ["progress", "blocked"],
                "done": ["progress", "review", "testing", "done"]}[final]
        prev = "open"
        for k, b in enumerate(path):
            if final == "blocked" and b == "blocked":
                d = ago(blocked_days[sum(1 for i in issues if i["bucket"] == "blocked") % len(blocked_days)])
            elif k == len(path) - 1 and final != "done":
                d = ago(rnd.choice([0, 1, 1, 2, 4, 5]))
            else:
                d = min(day, t + dt.timedelta(days=rnd.randint(0, 2)))
                while d.weekday() >= 5:
                    d += dt.timedelta(days=1)
                d = min(d, day)
            t = d
            hist.append({"at": stamp(d, 10 + k * 2, 15), "from": STATUS[prev], "to": STATUS[b], "by": who or PEOPLE[0]})
            prev = b
        comments = []
        if final == "blocked":
            comments.append({"at": hist[-1]["at"], "by": who, "body": REASONS[n % len(REASONS)]})
        issues.append({"key": key, "title": title, "type": "Задача", "subtask": False, "status": STATUS[final],
                       "bucket": final, "assignee": who, "sp": sp, "epic": epic_keys[n % len(epic_keys)],
                       "created": created, "entered": entered, "left": None, "history": hist, "comments": comments})
    epics = []
    for n, (title, due) in enumerate(EPICS):
        key = epic_keys[n]
        kids = [{"key": i["key"], "status": i["status"],
                 "category": "done" if i["bucket"] == "done" else "todo" if i["bucket"] == "open" else "work",
                 "bucket": i["bucket"], "assignee": i["assignee"], "created": i["created"][:10],
                 "doneAt": i["history"][-1]["at"][:10] if i["bucket"] == "done" else None, "inSprint": True}
                for i in issues if i["epic"] == key]
        for m in range(4 + n * 2):                         # объём эпика вне спринта: закрытое раньше и будущее
            done = m % 3 != 2
            when = (day - dt.timedelta(days=rnd.randint(2, 40))).isoformat()
            kids.append({"key": f"ALF-{400 + n * 20 + m}", "status": STATUS["done" if done else "open"],
                         "category": "done" if done else "todo", "bucket": "done" if done else "open",
                         "assignee": PEOPLE[(n + m) % len(PEOPLE)], "created": (day - dt.timedelta(days=60)).isoformat(),
                         "doneAt": when if done else None, "inSprint": False})
        epics.append({"key": key, "title": title, "due": (day + dt.timedelta(days=due)).isoformat(), "children": kids})
    return {
        "schema": 1, "team": {"slug": "alpha", "name": "Альфа"}, "jira": "https://jira.example.com", "board": 1,
        "collectedAt": collected.isoformat() + "+03:00", "unit": "SP",
        "statusBuckets": {v: k for k, v in STATUS.items()},
        "sprint": {"id": 1, "name": f"Альфа {start:%y}.{start.isocalendar()[1]:02d}", "start": start.isoformat(), "end": end.isoformat()},
        "issues": issues, "epics": epics,
    }


def promises(day=None):
    day = day or dt.date.today()
    return {"alpha": [
        {"id": "P-1", "who": "Громов Кирилл", "what": "Довести оплату в один клик до стенда приёмки",
         "due": (day - dt.timedelta(days=3)).isoformat()},
        {"id": "P-2", "who": "Котов Денис", "what": "Закрыть баги регресса личного кабинета", "due": day.isoformat()},
        {"id": "P-3", "who": "Белова Мария", "what": "Согласовать контракт API с партнёром",
         "due": (day + dt.timedelta(days=2)).isoformat()},
    ]}
