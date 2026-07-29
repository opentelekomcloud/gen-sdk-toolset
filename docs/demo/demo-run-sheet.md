# Demo Run-Sheet — gen-sdk-toolset (панель + сканер)

**Формат:** ~30 минут · слайды на английском · живое демо на реальных данных (docker compose, Postgres, отсканированные репозитории `opentelekomcloud-docs`).

---

## Принцип разделения: что в PPT, что на живом сайте

**В слайды идёт то, чего не видно в UI:** контекст и проблема, схема пайплайна, архитектура, принципы качества данных, инженерные практики, роадмап, цифры-итоги. Слайды также страхуют демо: скриншоты ключевых экранов лежат в backup-секции на случай, если что-то не поднимется.

**На живом сайте показываем всё интерактивное** — то, что на скриншоте выглядит мёртвым, а вживую продаёт продукт: фильтры и поиск реестра, drill-down до конкретного документа и IR-таблицы, живой запуск rescan с job-спиннером, переключение генераций.

| Контент | Где | Почему |
|---|---|---|
| Проблема, зачем проект, пайплайн docs→scan→panel→SDK | PPT | Контекст, в UI не виден |
| Архитектура и стек | PPT | Схема нагляднее живого кода |
| Принцип «data never disappears silently», взвешивание качества | PPT | Концепция, объясняется до демо |
| Реестр сервисов: фильтры, поиск, сортировка, quality-бары | **Сайт** | Интерактив, главный экран |
| Attention band («requires attention») | **Сайт** | Живой список, сам себя объясняет |
| Страница сервиса: метрики, секции, top issues | **Сайт** | Drill-down впечатляет вживую |
| Документ → секции → IR-таблица параметров → ссылка на исходник | **Сайт** | Кульминация: от цифры к первоисточнику |
| **Живой rescan**: кнопка → job #N → спиннер → обновление | **Сайт** | Самый сильный момент демо |
| Селектор генераций, откат на старый снапшот | **Сайт** | Показывает зрелость: история, безопасность |
| Exclude-flow | Сайт, бегло / пропустить | Второстепенно, только если время есть |
| Swagger `/docs` | PPT (одна строка) или 10 сек в браузере | Для технарей в зале |
| Инженерное качество (тесты, coverage-гейты, CI) | PPT | В UI не видно |
| Роадмап (Generation, Maintenance, discovery) | PPT | Табы «soon» видны на сайте — сослаться |
| Итоговые цифры скана | PPT (стат-слайд) | Впечатление «до/после» |

---

## Тайминг (30 мин)

| Время | Блок | Носитель |
|---|---|---|
| 0–3 мин | Слайды 1–3: проблема, видение, пайплайн | PPT |
| 3–7 мин | Слайды 4–6: что построено, сканер, панель-концепции | PPT |
| 7–8 мин | Слайд 7: «What you'll see now» — план демо | PPT |
| 8–20 мин | **Живое демо** (сценарий ниже) | Сайт |
| 20–23 мин | Слайды 9–10: архитектура, инженерное качество | PPT |
| 23–27 мин | Слайды 11–15: цифры организации, **fix-list 527 ячеек (слайд 12)**, две цепочки генератора, A/B, роадмап | PPT |
| 27–30 мин | Слайд 16: asks + Q&A | PPT |

Примечания:
- Слайд 11 — реальные цифры скана: 96 → 83 → 5 556 файлов → 3 475 эндпоинт-документов → 2 651 без единой ошибки; 47/32 сервисов целиком; 2 заблокированы файлами >1 МБ. **Сверить со свежим сканом перед встречей.**
- Слайд 12 — 527 ячеек с типами вне конвенции по 34 сервисам + разбивка (List<x> — 170, синонимы — 126, Table N — 67, имя вложенной структуры — ~60, описание словами — 31, внутренние маркеры — 17). Это сильнейший «зачем это всё» момент: панель выдаёт backlog для доков с точностью до строки.
- Слайд 13 «Two pipelines on the table» — обе цепочки (A: Jinja-first, B: LLM-primary) равноправно; внизу инварианты. Детали — в `docs/gen_pipeline.md` и спикерских заметках.
- Слайд 14 — trade-offs A vs B и план A/B на контрастных сервисах: `application-service-mesh` (docs 100% · parser 100%) и `dedicated-host` (docs 61% · parser 100%). Подача: «мы не спорим о стратегии — мы её измерим».
- Внизу слайда 14 — блок про Qwen3.6-35B: self-hosted за LiteLLM-гейтвеем (2 GPU-ноды), бенчмарки — сильный файловый кодинг (SWE-bench ~73%), заметно слабее генерация целого репозитория (NL2Repo ~29 — ровно риск варианта B); session stickiness на ключ ограничивает параллелизм; prefill-bound на длинном контексте → выгодны маленькие сфокусированные промпты. Детали и цифры — в спикерских заметках. **API-ключ гейтвея нигде не показывать и не коммитить.**
- На слайдах 6 и 13 упомянуто: quality считается только по таблицам параметров, example-блоки исключены из скора (их issues остаются видимыми). Если спросят «почему» — example — это evidence, генератор строит код из таблиц; сломанный пример ничего не говорит о генерируемости сервиса.

---

## Сценарий живого демо (12 минут)

Подготовка **до** встречи — см. чеклист ниже.

1. **Реестр** (`/scan`) — 3 мин.
   Talk track: *"This is the registry — every OTC docs repository that has an API reference, discovered automatically. Each row: scan status, document count, quality share, and a per-section health strip."*
   Действия: пройтись по фильтрам (Failed → Partial → All), поиск по имени, сортировка «worst quality first». Показать легенду ok/partial/failed.

2. **Attention band** — 1 мин, **по обстоятельствам**. Показывать только то, что реально есть в данных.
   Что точно есть: **2 сервиса с файлами >1 МБ** — они висят как failed / «failed and hold no data», это честная иллюстрация правила.
   *"The panel computes what needs a human. These two services failed — their docs contain files over 1 MB, a scanner limitation we know about and track. Nothing is hidden: they sit here until we handle them."*
   Правила «старая версия сканера» и «docs drift» без подходящих данных вживую не показать — упомянуть словами одной фразой (*"the same band lights up when a service was scanned by an older scanner version, or when the docs moved ahead of the last scan"*) или заготовить скриншот в backup. Не пытаться изобразить вживую.

3. **Страница сервиса** — 3 мин. Выбрать заранее сервис с богатыми данными (и с partial-документами; в идеале — с «≤» в метрике качества).
   *"Top: the active scan generation — every successful scan is persisted, nothing is overwritten. Metrics: endpoint documents, clean-docs share, status breakdown. Section cards show where documentation breaks down — path params are usually fine, response bodies are where quality drops."*
   **Ключевой момент (отсылка к слайду 6):** показать значок **«≤»** у clean-docs и строку **«X in full · Y rows unread · Z not read»** под счётчиком документов.
   *"Note the ≤ sign: this service has content our parser couldn't read yet — so we report quality as an honest upper bound, not a point estimate. The panel never confuses 'we read it and the doc is broken' with 'we couldn't read it — there may be more'. The first is counted against the documentation; the second against our scanner, and it's our backlog for extending the parser."*
   Действия: навести на «≤» (tooltip объясняет границу), клик по счётчику секции → фильтр документов; клик по top-issue chip — можно показать, что среди issue-кодов есть и doc-defects, и scanner-gaps (unmapped_block, unsupported_doc_style).

4. **Документ → IR** — 2 мин.
   *"Down to a single document: every parameter table the scanner extracted — field, type, required, description. This is the exact input the SDK generator will consume. And here's the source link — same commit that was scanned, full traceability."*

5. **Живой rescan** — 2 мин. Взять маленький сервис (сканируется быстро, напр. anti-ddos).
   *"Now live: I trigger a rescan. The API returns a job id immediately; the panel polls the job. ... Done — a new generation appeared, the registry refreshed."*
   Действия: Force rescan → показать job #N спиннер → дождаться → открыть селектор генераций, показать новую запись.

6. **Генерации / откат** — 1 мин.
   *"If a new scan ever looks wrong, we can activate any older snapshot — no rescan, nothing deleted, switch back anytime."*
   Действия: открыть попап генераций, показать confirm при выборе старой (можно не активировать).

**Запасные пути, если что-то падает:**
- Rescan не стартует / GitHub rate limit → сказать *"we hit the GitHub rate limit — exactly the failure mode the panel is designed to surface"* и показать failed-баннер (это тоже фича!), дальше по скриншотам.
- Стек не поднялся → backup-слайды со скриншотами (добавить перед встречей) или `MOCK_API=1` (без живого rescan).

**Что НЕ планируем показывать вживую** (нет данных / нельзя вызвать по заказу): attention-правила «старая версия сканера» и «docs drift»; типизированные interruption-баннеры (rate limit / auth). Если rate limit случится сам — это подарок, обыграть как фичу; иначе — одна фраза словами или скриншот в backup.

---

## Чеклист подготовки (за день до демо)

- [ ] `docker compose up --build`, проверить `GITHUB_TOKEN` в `.env` (свежий, лимиты не выбраны).
- [ ] `uv run panel discover` — реестр заполнен; сканы прогнаны. Сверить цифры слайдов 11–12 (96 / 83 / 5 556 / 3 475 / 2 651 / 47 / 32 / 2 / 527 / 34 и разбивку отклонений) и проценты ASM / dedicated-host на слайде 14 со свежими данными панели.
- [ ] Выбрать: «богатый» сервис для drill-down + «маленький» сервис для живого rescan (быстрый скан). Для drill-down желательно взять сервис, у которого качество показывается как «≤ N%» (есть unread-контент) — на нём демонстрируется различие «док не ок» vs «мы не смогли прочесть» со слайда 6.
- [ ] Цифры уже вписаны в слайды 11–12 (по скану от 29.07) — если перед демо прогонялись новые сканы, обновить их и версию сканера в подписи.
- [ ] Сделать 4–5 скриншотов (реестр, страница сервиса, IR-таблица, rescan-спиннер, генерации) и добавить в backup-слайды.
- [ ] Прогнать демо один раз целиком с таймером.
- [ ] Закрыть лишние вкладки, зум браузера ~110–125%, выключить нотификации.
