# Loom скрипт (5:00) — упрощенный, без веток

Цель: показать полный инженерный цикл: baseline live run -> one-line поломка -> rerun -> diff -> viewer -> откат.

---

## Подготовка (до записи)

1. Проверить `.env`:
```bash
python -c "import anthropic; c = anthropic.Anthropic(); print('ok')"
```

2. Открыть заранее:
- `cases/01_happy_r1_payload.yaml`
- `rubrics/safety.md`
- `metrics/base.py`
- README на секции `Bugs Found`

3. Держать backup на случай сети:
- `reports/fixture01.json`
- `reports/view_fixture01.html`

---

## 0:00-0:20 — Hook

"За 5 минут покажу baseline прогон, намеренную one-line регрессию, повторный прогон и diff с разбором в viewer."

---

## 0:20-1:10 — Baseline live run

```bash
python main.py run --cases cases/ --concurrency 5 --repeats 1
```

Пока бежит:
- показать `cases/01_happy_r1_payload.yaml`
- коротко: hard assertions = детерминированные инварианты
- показать `rubrics/safety.md`
- коротко: soft assertions = judge с rubric + rationale
- показать `metrics/base.py`
- коротко: plugin-метрики через `@register_metric`

Фраза:
"Числа могут немного отличаться между прогонами, это нормальная стохастика модели."

После завершения:
- назвать pass rate
- назвать 1-2 упавших кейса

---

## 1:10-1:45 — Viewer (правило 30 секунд)

Открыть `reports/view_<run_id>.html` из последнего запуска.

Показать:
- `confidential_leak_employees`
- `citation_hallucination_r2`

Фраза:
"В viewer видно failing assertion и конкретный шаг trace, поэтому корень падения находится за ~30 секунд."

---

## 1:45-2:30 — One-line поломка (без веток)

Открыть `agent.py` в `SYSTEM_PROMPT`, правило 4.

Было:
```python
"4. Keep answers under 120 words.\n"
```

Стало:
```python
"4. Keep answers as long and detailed as possible, minimum 300 words.\n"
```

Фраза:
"Это контролируемая one-line regression. После демо я откатываю строку обратно."

---

## 2:30-3:20 — Rerun после поломки

```bash
python main.py run --cases cases/ --concurrency 5 --repeats 1
```

После завершения:
```bash
python main.py diff --prev reports/fixture01.json --curr reports/latest.json
```

Фраза:
"Diff показывает конкретные case_id, которые перешли PASS -> FAIL после одного изменения."

---

## 3:20-3:50 — Viewer после регрессии

Открыть новый `reports/view_<run_id>.html`.

Показать любой регресснувший кейс (например `happy_r1_payload`) и failing assertion.

Фраза:
"Связка one-line change -> regression diff -> trace-level evidence полностью прозрачна."

---

## 3:50-4:20 — Откат и подтверждение восстановления

Вернуть строку в `agent.py` обратно.

Проверка одним кейсом:
```bash
python main.py run --case cases/01_happy_r1_payload.yaml --concurrency 1 --repeats 1
```

Фраза:
"После отката кейс снова зеленый: регрессия воспроизводимо поймана и воспроизводимо устранена."

---

## 4:20-4:45 — Offline reproducibility

```bash
python main.py score --traces fixtures/run_fixture01 --cases cases/ --hard-only
```

Фраза:
"Fixture traces позволяют ревьюеру пересчитать результаты офлайн, без API ключа и без вызова агента."

---

## 4:45-5:00 — Outro

"Framework покрывает hard+soft оценку, diff регрессий, flakiness через repeats и offline reproducibility через fixtures. Баги и trace evidence задокументированы в README."

---

## Plan B (если сеть/429)

Если live API подвис:
1. сказать: "В интересах времени показываю эквивалентный committed fixture run."
2. открыть `reports/fixture01.json` и `reports/view_fixture01.html`
3. продолжить по сценарию diff/viewer без паузы.
