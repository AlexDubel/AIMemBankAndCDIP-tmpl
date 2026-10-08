<div align="center">

🌐 [English](README.md) · **[ Українська ]**

# Шаблон проєкту з AI Memory Bank та CDIP

### Попередньо налаштований стартовий репозиторій для розробки з AI-асистентами: Antigravity, Claude Code, Cline, Cursor та Gemini.

[![Протокол: 3.2](https://img.shields.io/badge/protocol-3.2-6366f1?style=flat-square)](MemBankRulesUkr.md)
[![Ліцензія: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Валідатор: Python 3.10+](https://img.shields.io/badge/validator-Python%203.10%2B-3776ab?style=flat-square)](tools/validate_protocol.py)

</div>

---

## Вітаємо у вашому новому проєкті!

Цей репозиторій створено на основі шаблону **Shared AI Memory Bank з розширенням CDIP**. Він містить:
- **Канонічну точку входу:** `AGENTS.md` (делегує правила специфікаціям версії 3.2).
- **Тонкі адаптери інструментів:** готові файли для `CLAUDE.md`, `GEMINI.md`, `.clinerules/` та `.cursor/rules/`.
- **Попередньо створену структуру Memory Bank:** каталог `memory-bank/` зі стартовими файлами для опису місії проєкту, продуктового контексту, архітектурних патернів і технологічного стека.
- **Ієрархію вимог CDIP:** каталог `requirements/` (`BR/`, `SR/`, `tasks/`) для наскрізної простежуваності розробки.
- **Еталонний валідатор протоколу:** `tools/validate_protocol.py` для автоматичної перевірки цілісності документації та структури вимог.
- **Повні специфікації двома мовами:** українською (`MemBankRulesUkr.md`, `MemBankRulesWithCDIPUkr.md`) та англійською (`MemBankRules.md`, `MemBankRulesWithCDIP.md`).

---

## Швидкий старт (3 кроки)

### 1. Опишіть бачення вашого проєкту
Відкрийте файли `memory-bank/projectBrief.md` та `memory-bank/techContext.md`:
- Зафіксуйте **Місію**, **Цілі** та **Обмеження** проєкту.
- Вкажіть планований **Технологічний стек** (мови, фреймворки, команди запуску тестів та збірки).

### 2. Запустіть вашого AI-асистента
Відкрийте цей проєкт у **Google Antigravity**, **Claude Code**, **Cline** або **Cursor**:
- Надішліть асистенту запит:
  > *"Прочитай AGENTS.md та memory-bank/projectBrief.md. Підтвердь знайомство з протоколом та коротко підсумуй наш поточний фокус роботи."*
- Дотримуйтеся фаз робочого процесу згідно з `MemBankRulesUkr.md` (Plan Mode для аналізу, Act Mode для виконання завдань).

### 3. Перевірте документацію та вимоги
Запускайте валідатор для перевірки відповідності протоколу:

```bash
# Валідація файлів специфікації
python3 tools/validate_protocol.py --specs .

# Валідація артефактів memory-bank та вимог вашого проєкту
python3 tools/validate_protocol.py --artifacts .
```

---

## Першоджерело та оновлення

Канонічні специфікації протоколу, докладні посібники та оновлення знаходяться в основному репозиторії:
👉 **[AlexDubel/multipleAImembank](https://github.com/AlexDubel/multipleAImembank)**
