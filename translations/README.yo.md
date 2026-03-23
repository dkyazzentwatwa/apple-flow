<div align="center">

# Apple Flow

**Olùrànlọwọ AI rẹ abinibi Apple**

Ṣakoso AI lati iMessage, Mail, Awọn olurannileti, Awọn akọsilẹ, ati Kalẹnda lori macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow jẹ daemon macOS ti o fẹran agbegbe agbegbe, ti o so awọn ohun elo Apple pọ si awọn CLI AI (Codex, Claude, Gemini, Cline, ati Kilo). O fi agbara mu awọn atokọ funfun ti awọn olufiranṣẹ, awọn ẹnu-ọna ifọwọsi fun awọn iṣẹ iyipada, ati awọn ihamọ aaye iṣẹ nipasẹ aiyipada.

## Awọn sikirini

| Dasibodu | Iṣakoso Iṣẹ-ṣiṣe |
|---|---|
| ![Dasibodu Apple Flow](docs/screenshots/dashboard.png) | ![Iṣakoso Iṣẹ-ṣiṣe Apple Flow](docs/screenshots/task-management.png) |

| Àkọsílẹ̀ Òfin AI | Ìṣẹ̀lẹ̀ Kàlẹ́ńdà |
|---|---|
| ![Àkọsílẹ̀ Òfin AI Apple Flow](docs/screenshots/ai-policy-log.png) | ![Ìṣẹ̀lẹ̀ Kàlẹ́ńdà Apple Flow](docs/screenshots/calendar-event.png) |

| Àròkọ Ọ́fíìsì |
|---|
| ![Àròkọ Ọ́fíìsì Apple Flow](docs/screenshots/office-brainstorm.png) |

### Ìfilọ́lẹ̀ Dasibodu

| Ìfúnlápá 1 | Ìfúnlápá 2 |
|---|---|
| ![Ìfúnlápá Apple Flow ìgbésẹ̀ 1](docs/screenshots/onboarding-apple-flow1.png) | ![Ìfúnlápá Apple Flow ìgbésẹ̀ 2](docs/screenshots/onboarding-apple-flow2.png) |

| Ìfúnlápá 3 | Ìfúnlápá 4 |
|---|---|
| ![Ìfúnlápá Apple Flow ìgbésẹ̀ 3](docs/screenshots/onboarding-apple-flow3.png) | ![Ìfúnlápá Apple Flow ìgbésẹ̀ 4](docs/screenshots/onboarding-apple-flow4.png) |

| Ìṣètò Ìfiwọlé | Àṣìṣe Ìfúnlápá |
|---|---|
| ![Ìṣètò Ìfiwọlé ìfilọ́lẹ̀ Apple Flow](docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Àṣìṣe ìfúnlápá Apple Flow](docs/screenshots/apple-flow-onboarding-error..png) |

## Awọn akọkọ (Kika Iyara)

- Adaṣiṣẹ AI abinibi ti Apple, ti o fẹran agbegbe akọkọ, pẹlu awọn aiyipada aabo to lagbara (atokọ funfun + awọn ẹnu-ọna ifọwọsi + awọn aala aaye iṣẹ).
- Awọn iṣẹ-ṣiṣe ọpọ-ọna abawọle nipasẹ iMessage, Mail, Awọn olurannileti, Awọn akọsilẹ, ati Kalẹnda pẹlu awọn ṣiṣan irinṣẹ ti o pinnu.
- Atilẹyin Apple Pages tuntun fun iṣelọpọ iwe-ipamọ didara ga lati Markdown, pẹlu awọn akori, atokọ akoonu, awọn itọka, awọn okeere, ati awọn imudojuiwọn apakan.
- Atilẹyin Apple Numbers tuntun fun iṣelọpọ iwe-iṣẹ, iṣakoso iwe, awọn ilana ifisipo ori ila, ati adaṣiṣẹ ara.
- Awọn akopọ ogbon agbaye fun awọn iṣẹ-ṣiṣe ara Codex/Claude, pẹlu awọn ogbon `apple-flow-pages`, `apple-flow-numbers`, `apple-flow-mail`, ati `apple-flow-gateways`.
- Awọn iṣẹ-ṣiṣe ti o ṣetan fun iṣelọpọ pẹlu awọn iṣakoso iṣẹ, awọn irinṣẹ ilera/ipo, ati agbegbe idanwo pipe.

## Bẹrẹ Nibi

Yan ọna iṣeto kan:

| Ọna | Ti o dara julọ fun | Akoko | Ibi Iwọle |
|---|---|---:|---|
| **Iṣeto itọsọna AI (niyanju)** | Pupọ julọ awọn olumulo, ifisi ailewu julọ | ~10 iṣẹju | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Iwe afọwọkọ aṣẹ kan** | Fifi sori ẹrọ agbegbe/ibẹrẹ aifọwọyi ni iyara | ~5-10 iṣẹju | `./scripts/setup_autostart.sh` |
| **Iṣeto Afọwọyi** | Awọn agbegbe ilọsiwaju/aṣa | ~15+ iṣẹju | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Ibẹrẹ Iyara (Itọsọna AI)

### 1) Awọn ohun ti a beere tẹlẹ

- macOS pẹlu iMessage ti wọle
- 10 iṣẹju
- Homebrew + Python 3.11 + Node

```bash
# Fi Homebrew sori ẹrọ (ti o ba nilo)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Fi Python + Node sori ẹrọ
brew install python@3.11 node
```

### 2) Fi Olùsopọ́ AI CLI Kan Sori Ẹrọ

Yan ọkan:

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

- Kilo CLI (olùsopọ́ àgbékalẹ̀ àfikún)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Ṣe Afọwọkọ + Bibẹrẹ

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Pari iṣeto pẹlu Iyanjẹ Titunto si AI

Ṣii AI CLI rẹ ki o lẹẹ mọ:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Sisẹ yẹn ṣakoso:

- Awọn ayẹwo ilera (`wizard doctor --json`)
- Ipese kikun ti `.env` lati `.env.example`
- Awọn ẹnu-ọna ifọwọsi kedere ṣaaju kikọ/tun bẹrẹ
- Iṣeto orisun ẹnu-ọna (Awọn olurannileti/Awọn akọsilẹ/Kalẹnda)
- Ifọwọsi + ijẹrisi ipo iṣẹ

### 5) Fun Wiwọle Kikun si Disiki

1. Ṣii `Eto Eto -> Aṣiri & Aabo -> Wiwọle Kikun si Disiki`
2. Ṣafikun binary Python ti Apple Flow lo (jade iṣeto fihan ipa ọna)
3. Tan yipada

### 6) Idanwo Èéfín

Firanṣẹ ara rẹ ni iMessage:

```text
what files are in my home directory?
```

O yẹ ki o gba idahun laarin iṣẹju-aaya.

## Awọn ọna iṣeto (Alaye)

### A) Iwe afọwọkọ aṣẹ kan nikan

Ti o ko ba fẹ iṣeto ti AI ṣe itọsọna:

```bash
./scripts/setup_autostart.sh
```

Ti `.env` ba nsọnu, o n ṣe ifilọlẹ `python -m apple_flow setup` lati ṣe ipilẹṣẹ ọkan.

### B) Iṣeto Afọwọyi

Ṣatunkọ `.env` taara:

```bash
nano .env
```

Awọn bọtini ti o kere ju:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Fún àwọn iṣẹ́-ṣíṣe tí ó dá lórí Awọn olurannileti, `apple_flow_reminders_list_name` àti `apple_flow_reminders_archive_list_name` gbọ́dọ̀ jẹ́ àwọn orúkọ àtòjọpọ̀ tó rọrùn bíi `agent-task` àti `agent-archive`. Àwọn àtòjọpọ̀ tí a ti pín sí ìgbékalẹ̀, àwọn àtòjọpọ̀ tí a ti ṣe agọ́, àwọn ipa ọ̀nà tí a fi sí ara wọn, àti àwọn àyànfẹ́ tí ó dá lórí ìrọ̀rùn ìṣáṣe kò sí àtìlẹ́yìn.

Lẹhinna jẹrisi ki o tun bẹrẹ:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Awọn aṣẹ Akọkọ

| Aṣẹ | Ohun ti o ṣe |
|---|---|
| `<ohunkóhun>` | Iwiregbe adayeba |
| `idea: <iyanju>` | Àròkọ |
| `plan: <ibi-afẹde>` | Eto nikan (ko si iyipada) |
| `task: <ilana>` | Iṣẹ-ṣiṣe iyipada (ifọwọsi nilo) |
| `project: <sipesifikesonu>` | Iṣẹ-ṣiṣe igbesẹ-pupọ (ifọwọsi nilo) |
| `approve <id>` / `deny <id>` / `deny all` | Awọn iṣakoso ifọwọsi |
| `status` / `status <run_or_request_id>` | Ipo ṣiṣe/ibere |
| `health` | Ilera Daemon |
| `history: [ibere]` | Itan iwiregbe |
| `usage` | Awọn iṣiro lilo |
| `help` | Iranlọwọ + awọn imọran to wulo |
| `system: mute` / `system: unmute` | Awọn iṣakoso olùbágbé |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Awọn iṣakoso ṣiṣe |
| `system: cancel run <run_id>` | Fagilee ṣiṣe kan |
| `system: killswitch` | Pa gbogbo awọn ilana olupese ti nṣiṣe lọwọ |

### Ọna ipa-ọna ọpọ-aaye iṣẹ

Ṣaaju pẹlu `@alias`:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Awọn itọkasi faili pẹlu awọn orukọ inagijẹ

Ṣalaye awọn orukọ inagijẹ faili ninu `.env` nipasẹ `apple_flow_file_aliases` ki o si tọka si wọn ninu awọn iyanju pẹlu `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Awọn isopọ Aṣayan

Gbogbo awọn ẹnu-ọna iyan jẹ pipa nipasẹ aiyipada.

Iwa ti okunfa:

- Aami okunfa aiyipada ni `!!agent`
- Fun Mail/Awọn olurannileti/Awọn akọsilẹ/Kalẹnda, awọn ohun kan ti o ni aami yẹn nikan ni a ṣiṣẹ
- Aami ti yọkuro ṣaaju ipaniyan iyanju
- Tunto nipasẹ `apple_flow_trigger_tag`

Awọn apẹẹrẹ ti muu ṣiṣẹ:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Awọn apẹẹrẹ ifiranṣẹ ohun:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Lẹhinna tan pẹlu:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` sọ ọrọ gangan ti o firanṣẹ. `voice-task:` kọkọ ṣiṣẹ iṣẹ naa, lẹhinna firanṣẹ abajade ọrọ ati ẹda ohun ti a ṣapọ nipasẹ iMessage si nọmba oluwa ti a tunto.

Awọn apẹẹrẹ alabaṣepọ + iranti:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Iranti Canonical v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Apẹẹrẹ ṣiṣe asomọ:

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

Nigbati o ba ti ṣiṣẹ, Apple Flow n fa ọrọ-ọrọ ti iyanju jade lati awọn asomọ iMessage (awọn faili ọrọ/koodu, PDF, awọn aworan nipasẹ OCR nigbati o wa, awọn faili Office bii `.docx/.pptx/.xlsx`, ati awọn akọsilẹ ohun ohun nipasẹ gbigbe ohun Whisper CLI ti agbegbe) ati pẹlu ọrọ-ọrọ yẹn ninu iwiregbe, eto, ati awọn ṣiṣan ipaniyan ifọwọsi.

Ti iMessage ti n bọ ba jẹ akọsilẹ ohun kan, Apple Flow yoo kọ ọ silẹ ni bayi, yi i pada si ibeere `voice-task:` ti a ṣapọ, ati dahun pẹlu ọrọ mejeeji ati atẹle TTS ti a sọ. Fi `whisper` CLI ti agbegbe sori ẹrọ fun STT, gẹgẹ bi `pdftotext` ati `tesseract` ṣe lo fun awọn iru asomọ miiran.

Apẹẹrẹ itọju olùrànlọwọ:

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

Nigbati o ba ti ṣiṣẹ, Apple Flow n ṣiṣẹ ayẹwo itọju iwuwo fẹẹrẹ lori aago, tun ṣe atunṣe awọn oluranlọwọ ti o ti pẹ pẹlu rọra nigbati daemon ba wa ni imurasilẹ, ati ṣafihan telemetry oluṣọ ilọsiwaju siwaju nipasẹ `health` ati API abojuto. O tun le tan ipa ọna kanna pẹlu ọwọ pẹlu `system: recycle helpers` tabi `system: maintenance`.

Wo gbogbo awọn eto ni [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## Awọn ẹhin AI

| Olùsopọ́ | Koko |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (abinibi) | `apple_flow_connector=ollama` |

Awọn akọsilẹ:

- `codex-cli`, `claude-cli`, ati `gemini-cli` n ṣiṣe awọn aṣẹ alailopin.
- `cline` jẹ aṣoju ati atilẹyin awọn olupese pupọ.
- `kilo-cli` ni atilẹyin bi olùsopọ́, ṣugbọn aṣoṣeto iṣeto `generate-env` n ṣayẹwo lọwọlọwọ `claude-cli`, `codex-cli`, `gemini-cli`, `cline`, ati `ollama`. Fun `kilo-cli`, ṣeto awọn aaye olùsopọ́ nipasẹ kikọ iṣeto afọwọyi lẹhin iṣelọpọ.
- `ollama` nlo olùsopọ́ HTTP abinibi (`/api/chat`) pẹlu awoṣe aiyipada `qwen3.5:4b`.

## Ìgbékalẹ̀ Tó Dárajù

Jeki iṣeto ibẹrẹ wa ni tẹẹrẹ ki o rọrun lati jẹrisi idibo:

1. Bẹrẹ pẹlu iMessage nikan ki o jẹrisi pe `apple-flow service status --json` n ṣe ijabọ nipa daemon, iraye si DB Awọn ifiranṣẹ, ati idibo ti n ṣiṣẹ.
2. Mu ẹnu-ọna Apple kan ṣiṣẹ ni akoko kan lẹhin ti idibo ba ti duro.
3. Tan Olùbágbé, iranti, awọn atẹle, ati idanwo agbegbe ni ipari.

## Ìfilọ́lẹ̀ macOS Aṣayan

A pèsè ohun elo Swift ti agbegbe fun ifisi/dasibodu:

- Bundle ohun elo: `dashboard-app/AppleFlowApp.app`
- Zip ti o le pinpin: `dashboard-app/AppleFlowApp-macOS.zip`

Tàbí kọ/jáde láti àwọn ìwé àkọsílẹ̀ orísun: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Awọn Aiyipada Aabo

- Ifilọlẹ atokọ funfun olufiranṣẹ
- Awọn ihamọ aaye iṣẹ
- Iṣẹ-ṣiṣe ifọwọsi fun awọn iṣẹ iyipada
- Ijerisi olufọwọsi olufọwọsi
- Idinamọ oṣuwọn
- Wiwọle kika nikan si DB iMessage
- Ifinufindo-jade ni ilọpo meji

Awọn alaye: [SECURITY.md](SECURITY.md)

## Àkọsílẹ̀ Ayẹwo

Apple Flow n ṣe atilẹyin log analytics akọkọ-CSV lakoko ti o n tọju SQLite gẹgẹbi ile itaja ayẹwo canon.

- Orisun ayẹwo Canonical: tabili `events` SQLite (ipari ipari `/audit/events`).
- Digi atupale: `agent-office/90_logs/events.csv` (fikun-nikan, ila kan fun iṣẹlẹ kan).
- Digi Markdown ti eniyan le ka: alaabo nipasẹ aiyipada.

Awọn eto `.env` to wulo:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Iṣakoso Iṣẹ

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Awọn Iwe

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

## Imoran

Wo [CONTRIBUTING.md](CONTRIBUTING.md).

## Iwe-aṣẹ

MIT — wo [LICENSE](LICENSE).