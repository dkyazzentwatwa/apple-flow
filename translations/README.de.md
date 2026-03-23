<div align="center">

# Apple Flow

**Ihr Apple-nativer KI-Assistent**

Steuern Sie KI von iMessage, Mail, Erinnerungen, Notizen und Kalender unter macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow ist ein lokaler macOS-Daemon, der Apple-Apps mit KI-CLIs (Codex, Claude, Gemini, Cline und Kilo) verbindet. Er erzwingt standardmäßig Absender-Zulassungslisten, Genehmigungsschranken für modifizierende Arbeiten und Arbeitsbereichsbeschränkungen.

## Screenshots

| Dashboard | Aufgabenverwaltung |
|---|---|
| ![Apple Flow Dashboard](../docs/screenshots/dashboard.png) | ![Apple Flow Aufgabenverwaltung](../docs/screenshots/task-management.png) |

| KI-Richtlinienprotokoll | Kalenderereignis |
|---|---|
| ![Apple Flow KI-Richtlinienprotokoll](../docs/screenshots/ai-policy-log.png) | ![Apple Flow Kalenderereignis](../docs/screenshots/calendar-event.png) |

| Büro-Brainstorming |
|---|
| ![Apple Flow Büro-Brainstorming](../docs/screenshots/office-brainstorm.png) |

### Dashboard-App

| Onboarding 1 | Onboarding 2 |
|---|---|
| ![Apple Flow Onboarding Schritt 1](../docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow Onboarding Schritt 2](../docs/screenshots/onboarding-apple-flow2.png) |

| Onboarding 3 | Onboarding 4 |
|---|---|
| ![Apple Flow Onboarding Schritt 3](../docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow Onboarding Schritt 4](../docs/screenshots/onboarding-apple-flow4.png) |

| Setup-Konfiguration | Onboarding-Fehler |
|---|---|
| ![Apple Flow App Setup-Konfiguration](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Apple Flow Onboarding-Fehlerbildschirm](../docs/screenshots/apple-flow-onboarding-error..png) |

## Highlights (Kurzfassung)

- Lokale, Apple-native KI-Automatisierung mit starken Sicherheitsstandards (Zulassungsliste + Genehmigungsschranken + Arbeitsbereichsgrenzen).
- Multi-Gateway-Operationen über iMessage, Mail, Erinnerungen, Notizen und Kalender mit deterministischen Tool-Workflows.
- Neue Apple Pages-Unterstützung für hochwertige Dokumentengenerierung aus Markdown, einschließlich Themen, Inhaltsverzeichnissen, Zitaten, Exporten und Abschnittsaktualisierungen.
- Neue Apple Numbers-Unterstützung für die Erstellung von Arbeitsmappen, die Blattverwaltung, die Semantik der Zeileneinfügung und die Automatisierung der Formatierung.
- Globale Skill-Pakete für Codex/Claude-artige Workflows, einschließlich dedizierter `apple-flow-pages`-, `apple-flow-numbers`-, `apple-flow-mail`- und `apple-flow-gateways`-Skills.
- Produktionsfähige Operationen mit Dienststeuerungen, Health-/Status-Tools und umfassender Testabdeckung.

## Hier starten

Wählen Sie einen Setup-Pfad:

| Pfad | Am besten für | Zeit | Einstiegspunkt |
|---|---|---:|---|
| **KI-geführtes Setup (empfohlen)** | Die meisten Benutzer, sicherste Einarbeitung | ~10 Min. | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Ein-Befehl-Skript** | Schnelle lokale Installation/Autostart | ~5-10 Min. | `./scripts/setup_autostart.sh` |
| **Manuelles Setup** | Fortgeschrittene/benutzerdefinierte Umgebungen | ~15+ Min. | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Schnellstart (KI-geführt)

### 1) Voraussetzungen

- macOS mit angemeldetem iMessage
- 10 Minuten
- Homebrew + Python 3.11 + Node

```bash
# Homebrew installieren (falls benötigt)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python + Node installieren
brew install python@3.11 node
```

### 2) Einen KI CLI-Konnektor installieren

Wählen Sie einen:

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

- Kilo CLI (optionaler fortgeschrittener Konnektor)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Klonen + Bootstrapping

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Konfiguration mit dem Master-Prompt abschließen

Öffnen Sie Ihre KI-CLI und fügen Sie ein:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Dieser Workflow behandelt:

- Gesundheitsprüfungen (`wizard doctor --json`)
- Vollständige `.env`-Generierung aus `.env.example`
- Explizite Bestätigungsfreigaben vor Schreibvorgängen/Neustarts
- Gateway-Ressourcen-Setup (Erinnerungen/Notizen/Kalender)
- Validierung + Überprüfung des Dienststatus

### 5) Vollzugriff auf das Laufwerk gewähren

1. Öffnen Sie `Systemeinstellungen -> Datenschutz & Sicherheit -> Vollzugriff auf das Laufwerk`
2. Fügen Sie das von Apple Flow verwendete Python-Binary hinzu (die Setup-Ausgabe zeigt den Pfad an).
3. Aktivieren Sie den Schalter

### 6) Rauchtest

Senden Sie sich selbst eine iMessage:

```text
what files are in my home directory?
```

Sie sollten innerhalb von Sekunden eine Antwort erhalten.

## Setup-Pfade (detailliert)

### A) Nur Ein-Befehl-Skript

Wenn Sie kein KI-geführtes Setup wünschen:

```bash
./scripts/setup_autostart.sh
```

Wenn `.env` fehlt, wird `python -m apple_flow setup` gestartet, um eine zu generieren.

### B) Manuelles Setup

Bearbeiten Sie `.env` direkt:

```bash
nano .env
```

Minimale Schlüssel:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Für erinnerungsbasierte Workflows müssen `apple_flow_reminders_list_name` und `apple_flow_reminders_archive_list_name` einfache Listenamen der obersten Ebene sein, wie `agent-task` und `agent-archive`. Unterteilte Listen, gruppierte Listen, verschachtelte Pfade und zugänglichkeitsbasierte Fallbacks werden nicht unterstützt.

Dann validieren und neu starten:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Kernbefehle

| Befehl | Was er tut |
|---|---|
| `<anything>` | Natürlicher Chat |
| `idea: <prompt>` | Brainstorming |
| `plan: <goal>` | Nur Plan (keine Änderungen) |
| `task: <instruction>` | Ändernde Aufgabe (Genehmigung erforderlich) |
| `project: <spec>` | Mehrstufige Aufgabe (Genehmigung erforderlich) |
| `approve <id>` / `deny <id>` / `deny all` | Genehmigungssteuerungen |
| `status` / `status <run_or_request_id>` | Ausführungs-/Anforderungsstatus |
| `health` | Daemon-Gesundheit |
| `history: [query]` | Nachrichtenverlauf |
| `usage` | Nutzungsstatistiken |
| `help` | Hilfe + praktische Tipps |
| `system: mute` / `system: unmute` | Begleitsteuerungen |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Laufzeitsteuerungen |
| `system: cancel run <run_id>` | Eine Ausführung abbrechen |
| `system: killswitch` | Alle aktiven Anbieterprozesse beenden |

### Multi-Workspace-Routing

Mit `@alias` präfixieren:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Dateireferenzen mit Aliasen

Definieren Sie Datei-Aliase in `.env` über `apple_flow_file_aliases` und referenzieren Sie diese in Prompts mit `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Optionale Integrationen

Alle optionalen Gateways sind standardmäßig deaktiviert.

Trigger-Verhalten:

- Standard-Trigger-Tag ist `!!agent`
- Für Mail/Erinnerungen/Notizen/Kalender werden nur Elemente verarbeitet, die diesen Tag enthalten
- Tag wird vor der Prompt-Ausführung entfernt
- Konfigurieren Sie über `apple_flow_trigger_tag`

Beispiele für die Aktivierung:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Beispiele für Sprachnachrichten:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Dann auslösen mit:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` spricht den genauen Text, den Sie senden. `voice-task:` führt zuerst die Aufgabe aus und sendet dann sowohl das Textergebnis als auch eine synthetisierte Audioversion über iMessage an die konfigurierte Besitzertelefonnummer.

Begleiter + Speicher Beispiele:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Kanonischer Speicher v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Beispiel für die Anhangverarbeitung:

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

Wenn aktiviert, extrahiert Apple Flow den Prompt-Kontext aus iMessage-Anhängen (Text-/Codedateien, PDFs, Bilder über OCR, falls verfügbar, Office-Dateien wie `.docx/.pptx/.xlsx` und Audio-Sprachnotizen über die lokale Whisper CLI-Transkription) und fügt diesen Kontext in Chat-, Planungs- und Genehmigungs-Workflows ein.

Wenn eine eingehende iMessage nur eine Sprachnotiz ist, transkribiert Apple Flow sie nun, wandelt sie in eine synthetische `voice-task:`-Anfrage um und antwortet sowohl mit Text als auch mit einem gesprochenen TTS-Follow-up. Installieren Sie eine lokale `whisper`-CLI für STT, ähnlich wie `pdftotext` und `tesseract` für andere Anhangtypen verwendet werden.

Beispiel für Helferwartung:

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

Wenn aktiviert, führt Apple Flow in einem Timer eine leichte Wartungsprüfung durch, recycelt veraltete Helfer sanft, wenn der Daemon im Leerlauf ist, und exponiert Telemetrie zur Fortschrittsüberwachung über `health` und die Admin-API. Sie können denselben Pfad auch manuell mit `system: recycle helpers` oder `system: maintenance` auslösen.

Vollständige Einstellungen finden Sie in [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## KI-Backends

| Konnektor | Schlüssel |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (nativ) | `apple_flow_connector=ollama` |

Hinweise:

- `codex-cli`, `claude-cli` und `gemini-cli` führen zustandslose Befehle aus.
- `cline` ist agentisch und unterstützt mehrere Anbieter.
- `kilo-cli` wird als Konnektor unterstützt, aber der Setup-Assistent `generate-env` validiert derzeit `claude-cli`, `codex-cli`, `gemini-cli`, `cline` und `ollama`. Für `kilo-cli` konfigurieren Sie die Konnektorfelder durch manuelle Konfigurationsschreibung nach der Generierung.
- `ollama` verwendet einen nativen HTTP-Konnektor (`/api/chat`) mit dem Standardmodell `qwen3.5:4b`.

## Empfohlener Start

Halten Sie das anfängliche Setup eng, damit das Polling einfach zu überprüfen ist:

1. Beginnen Sie nur mit iMessage und bestätigen Sie, dass `apple-flow service status --json` den Daemon, den Nachrichten-DB-Zugriff und das aktive Polling meldet.
2. Aktivieren Sie jeweils ein Apple-Gateway, nachdem das Polling stabil ist.
3. Schalten Sie Begleiter, Speicher, Follow-ups und Umgebungs-Scanning zuletzt ein.

## Optionale macOS-App

Eine lokale Swift-Onboarding-/Dashboard-App ist gebündelt:

- App-Bundle: `dashboard-app/AppleFlowApp.app`
- Verteilbare Zip-Datei: `dashboard-app/AppleFlowApp-macOS.zip`

Oder erstellen/exportieren Sie aus den Quelldokumenten: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Sicherheitsstandards

- Erzwingung der Absender-Zulassungsliste
- Arbeitsbereichsbeschränkungen
- Genehmigungsworkflow für modifizierende Aufgaben
- Überprüfung des Genehmigungsabsenders
- Ratenbegrenzung
- Schreibgeschützter iMessage-DB-Zugriff
- Unterdrückung doppelter ausgehender Nachrichten

Details: [SECURITY.md](SECURITY.md)

## Audit-Protokollierung

Apple Flow unterstützt jetzt ein CSV-basiertes Analyseprotokoll, während SQLite als kanonischer Audit-Speicher beibehalten wird.

- Kanonische Audit-Quelle: SQLite `events`-Tabelle (`/audit/events`-Endpunkt).
- Analyse-Spiegel: `agent-office/90_logs/events.csv` (nur anhängen, eine Zeile pro Ereignis).
- Menschlich lesbarer Markdown-Spiegel: standardmäßig deaktiviert.

Relevante `.env`-Einstellungen:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Dienstverwaltung

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Dokumentation

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

## Mitwirken

Siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Lizenz

MIT — siehe [LICENSE](LICENSE).