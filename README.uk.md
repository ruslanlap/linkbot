# LinkBot

[English](README.md) | Українська | [简体中文](README.zh-CN.md)

Перевірка HTTPS-посилань Markdown на постійні перенаправлення та 404. CLI, pre-commit і action типово не змінюють файли; `--fix` явно змінює локальні файли. Виконуються HTTPS GET-запити, мережевих записів немає.

## CLI

Потрібен Python 3.9+ і pip; основний код не має сторонніх залежностей:

```sh
python3 -m pip install .
linkbot
linkbot docs README.md
linkbot --fix docs
```

Перевіряйте diff. Код виходу: 0 — без знахідок (або виправлено і немає 404), 1 — перенаправлення в режимі перевірки або 404, 2 — помилка аргументів чи читання/запису. Мережеві помилки й непідтримувані посилання пропускаються: успіх не гарантує працездатності всіх посилань. Вивід містить кількість змінених посилань, файли та 404. При помилці пізнішого файлу попередні зміни можуть залишитися.

## pre-commit

Встановіть [pre-commit](https://pre-commit.com/), додайте `.pre-commit-config.yaml`, приклад закріплено на опублікованій версії:

```yaml
repos:
  - repo: https://github.com/ruslanlap/linkbot
    rev: v0.1.0
    hooks:
      - id: linkbot
```

Виконайте `pre-commit install` та `pre-commit run --all-files`. Хук перевіряє передані Markdown-файли, не редагує їх та індекс Git, зокрема частково staged файли. Виправляйте окремо через `linkbot --fix`, перевіряйте та додавайте зміни вручну. Мережеві перевірки можуть бути повільними або неповними офлайн.

## GitHub Action

Потрібні checkout, Python 3 і bash. Приклад закріплено на опублікованій версії:

```yaml
jobs:
  links:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - id: links
        uses: ruslanlap/linkbot@v0.1.0
        with:
          path: docs
```

`path` — файл або каталог, типово `.`. Вихід `exit-code` дорівнює 0, 1 чи 2; крок завершується помилкою при 1 і 2. Читати через `${{ steps.links.outputs.exit-code }}`; після помилки використовуйте `if: always()` або `continue-on-error`. Action не потребує токена чи прав на запис; `contents: read` потрібен checkout. Action не виправляє файли й не створює PR. Окремий `.github/workflows/linkbot.yml` цього репозиторію запускає `--fix` за розкладом/вручну і може створити PR з правами contents і pull-requests write та відповідним дозволом у налаштуваннях GitHub. Реальний GitHub не перевірено; лише 404 не створюють PR, дивіться summary.

## Межі

Лише прості inline HTTPS-посилання; зображення, URL із query, блоки коду, рядки з backtick та інший Markdown пропускаються. Виправляються лише 301/308 на той самий хост, що закінчуються 200. Якорі зберігаються, але не перевіряються; приватні адреси відхиляються. Деякі HTTP/мережеві помилки та недоступні каталоги не виявляються. Перевіряйте кожну зміну; не додавайте секрети в URL.

Експериментальний код розміщеного GitHub App у `ghapp/` збережено, але він не підтримується.

Для повного набору тестів встановіть `requirements.txt`, `pytest`, `pytest-subtests`, `pyyaml` і запустіть `python3 -m pytest -q`.
