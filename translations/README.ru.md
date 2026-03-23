<div align="center">

# Apple Flow

**Ваш Apple-нативный AI-помощник**

Управляйте ИИ из iMessage, Почты, Напоминаний, Заметок и Календаря на macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow — это локальный демон macOS, который связывает приложения Apple с CLI ИИ (Codex, Claude, Gemini, Cline и Kilo). Он принудительно применяет белые списки отправителей, шлюзы утверждения для изменяющих операций и ограничения рабочего пространства по умолчанию.

## Скриншоты

| Панель управления | Управление задачами |
|---|---|
| ![Панель управления Apple Flow](docs/screenshots/dashboard.png) | ![Управление задачами Apple Flow](docs/screenshots/task-management.png) |

| Журнал политики ИИ | Событие календаря |
|---|---|
| ![Журнал политики ИИ Apple Flow](docs/screenshots/ai-policy-log.png) | ![Событие календаря Apple Flow](docs/screenshots/calendar-event.png) |

| Офисный мозговой штурм |
|---|
| ![Офисный мозговой штурм Apple Flow](docs/screenshots/office-brainstorm.png) |

### Приложение панели управления

| Ввод в эксплуатацию 1 | Ввод в эксплуатацию 2 |
|---|---|
| ![Apple Flow ввод в эксплуатацию шаг 1](docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow ввод в эксплуатацию шаг 2](docs/screenshots/onboarding-apple-flow2.png) |

| Ввод в эксплуатацию 3 | Ввод в эксплуатацию 4 |
|---|---|
| ![Apple Flow ввод в эксплуатацию шаг 3](docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow ввод в эксплуатацию шаг 4](docs/screenshots/onboarding-apple-flow4.png) |

| Конфигурация установки | Ошибка ввода в эксплуатацию |
|---|---|
| ![Конфигурация установки приложения Apple Flow](docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Экран ошибки ввода в эксплуатацию Apple Flow](docs/screenshots/apple-flow-onboarding-error..png) |

## Основные моменты (краткий обзор)

- Локальная, нативная для Apple автоматизация ИИ с надежными настройками безопасности по умолчанию (белый список + шлюзы утверждения + границы рабочего пространства).
- Многошлюзовые операции через iMessage, Почту, Напоминания, Заметки и Календарь с детерминированными потоками инструментов.
- Новая поддержка Apple Pages для высококачественной генерации документов из Markdown, включая темы, оглавления, цитаты, экспорт и обновления разделов.
- Новая поддержка Apple Numbers для создания рабочих книг, управления листами, семантики вставки строк и автоматизации стиля.
- Глобальные пакеты навыков для рабочих процессов в стиле Codex/Claude, включая специализированные навыки `apple-flow-pages`, `apple-flow-numbers`, `apple-flow-mail` и `apple-flow-gateways`.
- Готовые к производству операции с элементами управления службами, инструментами мониторинга состояния/статуса и полным покрытием тестов.

## Начните здесь

Выберите один путь установки:

| Путь | Лучше всего для | Время | Точка входа |
|---|---|---:|---|
| **Установка с помощью ИИ (рекомендуется)** | Большинство пользователей, самый безопасный способ начать | ~10 мин | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Скрипт одной командой** | Быстрая локальная установка/автозапуск | ~5-10 мин | `./scripts/setup_autostart.sh` |
| **Ручная установка** | Продвинутые/пользовательские среды | ~15+ мин | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Быстрый старт (с помощью ИИ)

### 1) Предварительные требования

- macOS с авторизованным iMessage
- 10 минут
- Homebrew + Python 3.11 + Node

```bash
# Установить Homebrew (при необходимости)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Установить Python + Node
brew install python@3.11 node
```

### 2) Установить один CLI-коннектор ИИ

Выберите один:

- Claude CLI

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude auth login
```

- Codex CLI

```bash
npm install -g @openai/codex
codex login
```

- Gemini CLI

```bash
npm install -g @google/gemini-cli
gemini auth login
```

- Cline CLI

```bash
npm install -g cline
cline auth
```

- Kilo CLI (дополнительный расширенный коннектор)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Клонировать + Инициализировать

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Завершить настройку с помощью мастер-промпта ИИ

Откройте свой ИИ CLI и вставьте:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Этот поток обрабатывает:

- Проверки работоспособности (`wizard doctor --json`)
- Полную генерацию `.env` из `.env.example`
- Явные подтверждающие шлюзы перед записью/перезапуском
- Настройку ресурсов шлюза (Напоминания/Заметки/Календарь)
- Валидацию + проверку статуса службы

### 5) Предоставить полный доступ к диску

1. Откройте `Системные настройки -> Конфиденциальность и безопасность -> Полный доступ к диску`
2. Добавьте исполняемый файл Python, используемый Apple Flow (путь отображается в выводе установки)
3. Включите переключатель

### 6) Дымовой тест

Отправьте себе сообщение в iMessage:

```text
what files are in my home directory?
```

Вы должны получить ответ в течение нескольких секунд.

## Пути установки (подробно)

### A) Только скрипт одной командой

Если вы не хотите установку с помощью ИИ:

```bash
./scripts/setup_autostart.sh
```

Если `.env` отсутствует, запускается `python -m apple_flow setup` для его генерации.

### B) Ручная установка

Отредактируйте `.env` напрямую:

```bash
nano .env
```

Минимальные ключи:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Для рабочих процессов, основанных на Напоминаниях, `apple_flow_reminders_list_name` и `apple_flow_reminders_archive_list_name` должны быть простыми именами списков верхнего уровня, такими как `agent-task` и `agent-archive`. Разделенные списки, сгруппированные списки, вложенные пути и резервные варианты, основанные на доступности, не поддерживаются.

Затем проверьте и перезапустите:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Основные команды

| Команда | Что она делает |
|---|---|
| `<что угодно>` | Естественный чат |
| `idea: <подсказка>` | Мозговой штурм |
| `plan: <цель>` | Только план (без изменений) |
| `task: <инструкция>` | Изменяющая задача (требуется утверждение) |
| `project: <спецификация>` | Многошаговая задача (требуется утверждение) |
| `approve <id>` / `deny <id>` / `deny all` | Управление утверждениями |
| `status` / `status <run_or_request_id>` | Статус выполнения/запроса |
| `health` | Состояние демона |
| `history: [запрос]` | История сообщений |
| `usage` | Статистика использования |
| `help` | Помощь + практические советы |
| `system: mute` / `system: unmute` | Управление компаньоном |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Управление средой выполнения |
| `system: cancel run <run_id>` | Отменить одно выполнение |
| `system: killswitch` | Завершить все активные процессы провайдера |

### Маршрутизация в нескольких рабочих пространствах

Префикс с `@alias`:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Ссылки на файлы с алиасами

Определите алиасы файлов в `.env` через `apple_flow_file_aliases` и ссылайтесь на них в подсказках с помощью `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Дополнительные интеграции

Все дополнительные шлюзы по умолчанию отключены.

Поведение триггера:

- Тег триггера по умолчанию — `!!agent`
- Для Mail/Reminders/Notes/Calendar обрабатываются только элементы, содержащие этот тег
- Тег удаляется перед выполнением подсказки
- Настроить с помощью `apple_flow_trigger_tag`

Примеры включения:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Примеры голосовых сообщений:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Затем запускается с помощью:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` произносит точный текст, который вы отправляете. `voice-task:` сначала выполняет задачу, затем отправляет как текстовый результат, так и синтезированную аудиокопию через iMessage на настроенный номер владельца.

Примеры компаньона + памяти:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Каноническая память v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Пример обработки вложений:

```env
apple_flow_enable_attachments=true
apple_flow_max_attachment_size_mb=10
apple_flow_attachment_max_files_per_message=6
apple_flow_attachment_max_text_chars_per_file=6000
apple_flow_attachment_max_total_text_chars=24000
apple_flow_attachment_enable_image_ocr=true
apple_flow_attachment_enable_audio_transcription=true
apple_flow_attachment_audio_transcription_command=whisper
apple_flow_attachment_audio_transcription_model=turbo
```

Если включено, Apple Flow извлекает контекст подсказки из вложений iMessage (текстовые/кодовые файлы, PDF, изображения с помощью OCR при наличии, офисные файлы, такие как `.docx/.pptx/.xlsx`, и аудио голосовые заметки через локальную транскрипцию Whisper CLI) и включает этот контекст в потоки чата, планирования и выполнения утверждения.

Если входящее сообщение iMessage — это просто голосовая заметка, Apple Flow теперь транскрибирует ее, преобразует в синтетический запрос `voice-task:` и отвечает как текстом, так и голосовым TTS-ответом. Установите локальный CLI `whisper` для STT, аналогично тому, как `pdftotext` и `tesseract` используются для других типов вложений.

Пример обслуживания помощника:

```env
apple_flow_enable_helper_maintenance=true
apple_flow_helper_maintenance_interval_seconds=900
apple_flow_helper_recycle_idle_seconds=600
apple_flow_helper_recycle_max_age_seconds=3600
apple_flow_watchdog_poll_stall_seconds=60
apple_flow_watchdog_inflight_stall_seconds=300
apple_flow_watchdog_event_loop_lag_seconds=5
apple_flow_watchdog_event_loop_lag_failures=3
```

Если включено, Apple Flow запускает легкую проверку обслуживания по таймеру, мягко перерабатывает устаревшие помощники, когда демон простаивает, и отображает телеметрию контроля прогресса через `health` и административный API. Вы также можете вручную запустить тот же путь с помощью `system: recycle helpers` или `system: maintenance`.

Полные настройки смотрите в [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## Бэкенды ИИ

| Коннектор | Ключ |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (нативный) | `apple_flow_connector=ollama` |

Примечания:

- `codex-cli`, `claude-cli` и `gemini-cli` выполняют бессостояние команды.
- `cline` является агентным и поддерживает несколько провайдеров.
- `kilo-cli` поддерживается как коннектор, но мастер установки `generate-env` в настоящее время проверяет `claude-cli`, `codex-cli`, `gemini-cli`, `cline` и `ollama`. Для `kilo-cli` настройте поля коннектора вручную после генерации.
- `ollama` использует нативный HTTP-коннектор (`/api/chat`) с моделью по умолчанию `qwen3.5:4b`.

## Рекомендуемый запуск

Держите начальную настройку узкой, чтобы было легко проверять опрос:

1. Начните только с iMessage и убедитесь, что `apple-flow service status --json` сообщает о демоне, доступе к базе данных сообщений и активном опросе.
2. Включайте по одному шлюзу Apple за раз после того, как опрос станет стабильным.
3. Включите Компаньона, память, последующие действия и окружающее сканирование в последнюю очередь.

## Дополнительное приложение macOS

В комплект входит локальное Swift-приложение для онбординга/панели управления:

- Пакет приложения: `dashboard-app/AppleFlowApp.app`
- Распространяемый Zip-архив: `dashboard-app/AppleFlowApp-macOS.zip`

Или соберите/экспортируйте из исходной документации: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Стандарты безопасности по умолчанию

- Применение белого списка отправителей
- Ограничения рабочего пространства
- Рабочий процесс утверждения для изменяющих задач
- Проверка отправителя утверждения
- Ограничение скорости
- Доступ только для чтения к базе данных iMessage
- Подавление дублирующихся исходящих сообщений

Подробности: [SECURITY.md](SECURITY.md)

## Журналирование аудита

Apple Flow теперь поддерживает журнал аналитики в формате CSV, сохраняя SQLite в качестве канонического хранилища аудита.

- Канонический источник аудита: таблица `events` SQLite (конечная точка `/audit/events`).
- Зеркало аналитики: `agent-office/90_logs/events.csv` (только добавление, одна строка на событие).
- Человекочитаемое Markdown-зеркало: по умолчанию отключено.

Соответствующие настройки `.env`:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Управление службами

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Документация

- [docs/README.md](docs/README.md)
- [docs/PROJECT_REFERENCE.md](docs/PROJECT_REFERENCE.md)
- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)
- [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md)
- [docs/QUICKSTART.md](docs/QUICKSTART.md)
- [docs/ENV_SETUP.md](docs/ENV_SETUP.md)
- [docs/SKILLS_AND_MCP.md](docs/SKILLS_AND_MCP.md)
- [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)
- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Вклад

См. [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).