---
title: Дейлик из снимка PO-Sprint-observe — HTML для вкладки «Блокаторы»
date: 2026-10-19
kind: feature
area: report
prs: []
tags: [observe, web, csp]
source: session
---

# Дейлик из снимка PO-Sprint-observe

## Ситуация

Владелец попросил вкладку «Блокаторы» в отчётах /sprints — «полностью из репозитория с дейликом в PDF».
Отчёт собирал данные из Jira сам и печатал PDF; в оболочке нужен тот же отчёт, на тех же данных, что «Спринт»
и «Бизнес», сразу после «Актуализировать».

## Решение

`sprint_report/observe.py` переводит команду снимка observe (runner actual-sprint) в снимок отчёта: задачи
спринта из `burndown.items`, история и комментарии из `epics[].stories[].events`, эпики из `scope`.
`python -m sprint_report observe --data … --team …` печатает HTML для экрана: листы A4 по центру, без скриптов.

## Подводные камни

- В снимке observe нет SP — сгорание числом задач; подзадачи не берутся.
- Страница встраивается под CSP `script-src 'self'`: inline-скрипт FIT убран, масштаб задаёт оболочка.

## Как проверить

`python3 -m unittest discover -s tests` (tests/test_observe.py) и на реальном снимке:
`python3 -m sprint_report observe --data sprint-report.data.json --team live > live.html`.
