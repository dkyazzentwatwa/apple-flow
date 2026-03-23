<div align="center">

# Apple Flow

**Msaidizi wako wa AI wa asili wa Apple**

Dhibiti AI kutoka iMessage, Barua pepe, Vikumbusho, Vidokezo, na Kalenda kwenye macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow ni daemon ya macOS inayopendelea mazingira ya ndani, inayounganisha programu za Apple na CLI za AI (Codex, Claude, Gemini, Cline, na Kilo). Inatekeleza orodha nyeupe za watumaji, lango za idhini kwa kazi zinazobadilisha mfumo, na vizuizi vya nafasi ya kazi kwa chaguo-msingi.

## Picha za skrini

| Dashibodi | Usimamizi wa Kazi |
|---|---|
| ![Dashibodi ya Apple Flow](../docs/screenshots/dashboard.png) | ![Usimamizi wa kazi wa Apple Flow](../docs/screenshots/task-management.png) |

| Kumbukumbu ya Sera ya AI | Tukio la Kalenda |
|---|---|
| ![Kumbukumbu ya Sera ya AI ya Apple Flow](../docs/screenshots/ai-policy-log.png) | ![Tukio la Kalenda ya Apple Flow](../docs/screenshots/calendar-event.png) |

| Akili za Ofisi |
|---|
| ![Akili za Ofisi za Apple Flow](../docs/screenshots/office-brainstorm.png) |

### Programu ya Dashibodi

| Kuunganisha 1 | Kuunganisha 2 |
|---|---|
| ![Apple Flow hatua ya 1 ya kuunganisha](../docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow hatua ya 2 ya kuunganisha](../docs/screenshots/onboarding-apple-flow2.png) |

| Kuunganisha 3 | Kuunganisha 4 |
|---|---|
| ![Apple Flow hatua ya 3 ya kuunganisha](../docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow hatua ya 4 ya kuunganisha](../docs/screenshots/onboarding-apple-flow4.png) |

| Usanidi wa Kuweka | Hitilafu ya Kuunganisha |
|---|---|
| ![Usanidi wa kuweka programu ya Apple Flow](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Skrini ya hitilafu ya kuunganisha ya Apple Flow](../docs/screenshots/apple-flow-onboarding-error..png) |

## Muhtasari (Soma Haraka)

- Uendeshaji wa AI wa asili wa Apple, unaopendelea mazingira ya ndani, na mipangilio dhabiti ya usalama (orodha nyeupe + lango za idhini + mipaka ya nafasi ya kazi).
- Operesheni za lango nyingi kupitia iMessage, Barua pepe, Vikumbusho, Vidokezo, na Kalenda zenye mtiririko thabiti wa zana.
- Msaada mpya wa Apple Pages kwa utengenezaji wa hati zenye ubora wa juu kutoka Markdown, ikiwa ni pamoja na mandhari, jedwali la yaliyomo, nukuu, usafirishaji, na masasisho ya sehemu.
- Msaada mpya wa Apple Numbers kwa uundaji wa vitabu vya kazi, usimamizi wa laha, semantiki ya kuingiza safu, na automatisering ya mtindo.
- Vifurushi vya ujuzi vya kimataifa kwa ajili ya mtiririko wa kazi wa mtindo wa Codex/Claude, ikiwa ni pamoja na ujuzi maalum wa `apple-flow-pages`, `apple-flow-numbers`, `apple-flow-mail`, na `apple-flow-gateways`.
- Operesheni tayari kwa uzalishaji zenye vidhibiti vya huduma, zana za afya/hali, na chanjo kamili ya majaribio.

## Anza hapa

Chagua njia moja ya kuweka:

| Njia | Bora kwa | Muda | Sehemu ya kuanzia |
|---|---|---:|---|
| **Kuweka kwa mwongozo wa AI (inapendekezwa)** | Watumiaji wengi, ujumuishaji salama zaidi | ~10 min | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Hati ya amri moja** | Usakinishaji wa haraka wa ndani/kuwasha kiotomatiki | ~5-10 min | `./scripts/setup_autostart.sh` |
| **Kuweka mwenyewe** | Mazingira ya hali ya juu/maalum | ~15+ min | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Anza haraka (mwongozo wa AI)

### 1) Mahitaji ya awali

- macOS yenye iMessage iliyoingia
- Dakika 10
- Homebrew + Python 3.11 + Node

```bash
# Sakinisha Homebrew (ikiwa inahitajika)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Sakinisha Python + Node
brew install python@3.11 node
```

### 2) Sakinisha Kiunganishi Kimoja cha AI CLI

Chagua moja:

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

- Kilo CLI (kiunganishi cha juu cha hiari)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Kuunganisha + Bootstrapping

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Kamilisha Usanidi kwa Kutumia Prompt Kuu ya AI

Fungua CLI yako ya AI na ubandike:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Mchakato huu unashughulikia:

- Ukaguzi wa afya (`wizard doctor --json`)
- Uzalishaji kamili wa `.env` kutoka `.env.example`
- Lango za uthibitisho wazi kabla ya uandishi/kuwasha upya
- Usanidi wa rasilimali za lango (Vikumbusho/Vidokezo/Kalenda)
- Uthibitishaji + uthibitishaji wa hali ya huduma

### 5) Ruhusu Ufikiaji Kamili wa Diski

1. Fungua `Mipangilio ya Mfumo -> Faragha na Usalama -> Ufikiaji Kamili wa Diski`
2. Ongeza faili ya Python inayotumiwa na Apple Flow (matokeo ya usanidi yanaonyesha njia)
3. Washa swichi

### 6) Jaribio la Moshi

Jitumie ujumbe kwenye iMessage:

```text
what files are in my home directory?
```

Unapaswa kupokea jibu ndani ya sekunde chache.

## Njia za Kuweka (Zilizoelezwa kwa Kina)

### A) Hati ya amri moja pekee

Ikiwa hutaki kuweka kwa mwongozo wa AI:

```bash
./scripts/setup_autostart.sh
```

Ikiwa `.env` inakosekana, inazindua `python -m apple_flow setup` ili kutengeneza moja.

### B) Kuweka mwenyewe

Hariri `.env` moja kwa moja:

```bash
nano .env
```

Vifunguo vidogo:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Kwa ajili ya kazi zinazotumia vikumbusho, `apple_flow_reminders_list_name` na `apple_flow_reminders_archive_list_name` lazima ziwe majina ya orodha rahisi ya ngazi ya juu kama vile `agent-task` na `agent-archive`. Orodha zilizogawanywa, orodha zilizopangwa, njia zilizowekwa kiota, na njia mbadala zinazotegemea ufikiaji hazitumiki.

Kisha thibitisha na uwashe upya:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Amri Kuu

| Amri | Inachofanya |
|---|---|
| `<chochote>` | Gumzo la asili |
| `idea: <prompt>` | Kujadili mawazo |
| `plan: <lengo>` | Mpango pekee (hakuna mabadiliko) |
| `task: <maelekezo>` | Kazi inayobadilisha (idhini inahitajika) |
| `project: <maelezo>` | Kazi ya hatua nyingi (idhini inahitajika) |
| `approve <id>` / `deny <id>` / `deny all` | Vidhibiti vya idhini |
| `status` / `status <run_or_request_id>` | Hali ya utekelezaji/ombi |
| `health` | Afya ya daemon |
| `history: [hoja]` | Historia ya ujumbe |
| `usage` | Takwimu za matumizi |
| `help` | Msaada + vidokezo vya vitendo |
| `system: mute` / `system: unmute` | Vidhibiti vya msaidizi |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Vidhibiti vya utekelezaji |
| `system: cancel run <run_id>` | Ghairi utekelezaji mmoja |
| `system: killswitch` | Zima michakato yote ya mtoa huduma inayofanya kazi |

### Uelekezaji wa nafasi nyingi za kazi

Weka kiambishi awali na `@alias`:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Marejeo ya faili na lakabu

Bainisha lakabu za faili katika `.env` kupitia `apple_flow_file_aliases` na uzirejee katika prompts kwa `f:<alias>@`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Viunganishi vya Hiari

Lango zote za hiari zimezimwa kwa chaguo-msingi.

Tabia ya kichochezi:

- Lebo ya kichochezi chaguomsingi ni `!!agent`
- Kwa Barua pepe/Vikumbusho/Vidokezo/Kalenda, ni vipengee tu vilivyo na lebo hiyo ndivyo vinavyochakatwa
- Lebo huondolewa kabla ya utekelezaji wa prompt
- Sanidi kupitia `apple_flow_trigger_tag`

Mifano ya kuwezesha:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Mifano ya ujumbe wa sauti:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Kisha anzisha kwa:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` inazungumza maandishi halisi unayotuma. `voice-task:` inaendesha kazi kwanza, kisha hutuma matokeo ya maandishi na nakala ya sauti iliyounganishwa kupitia iMessage kwa namba ya mmiliki iliyosanidiwa.

Mifano ya msaidizi + kumbukumbu:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Kumbukumbu ya msingi v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Mfano wa kuchakata viambatisho:

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

Ikishawezeshwa, Apple Flow huchota maudhui ya prompt kutoka viambatisho vya iMessage (faili za maandishi/code, PDF, picha kupitia OCR inapopatikana, faili za Ofisi kama `.docx/.pptx/.xlsx`, na memo za sauti kupitia unukuzi wa Whisper CLI ya ndani) na kujumuisha maudhui hayo katika soga, upangaji, na mtiririko wa utekelezaji wa idhini.

Ikiwa iMessage inayoingia ni memo ya sauti tu, Apple Flow sasa huinukuu, huibadilisha kuwa ombi la `voice-task:` bandia, na kujibu kwa maandishi na ufuatiliaji wa sauti wa TTS. Sakinisha `whisper` CLI ya ndani kwa STT, sawa na jinsi `pdftotext` na `tesseract` zinavyotumika kwa aina zingine za viambatisho.

Mfano wa matengenezo ya msaidizi:

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

Ikishawezeshwa, Apple Flow hufanya ukaguzi wa matengenezo mepesi kwa kutumia kipima muda, hurejesha wasaidizi waliozeeka kwa upole wakati daemon iko bila kazi, na hufichua telemetri ya ufuatiliaji wa maendeleo kupitia `health` na API ya msimamizi. Unaweza pia kuanzisha njia sawa mwenyewe na `system: recycle helpers` au `system: maintenance`.

Angalia mipangilio kamili katika [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## Backends za AI

| Kiunganishi | Kifunguo |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (asili) | `apple_flow_connector=ollama` |

Vidokezo:

- `codex-cli`, `claude-cli`, na `gemini-cli` huendesha amri zisizo na hali.
- `cline` ni wakala na inasaidia watoa huduma wengi.
- `kilo-cli` inatumika kama kiunganishi, lakini mchawi wa usanidi `generate-env` kwa sasa anathibitisha `claude-cli`, `codex-cli`, `gemini-cli`, `cline`, na `ollama`. Kwa `kilo-cli`, weka sehemu za kiunganishi kupitia uandishi wa usanidi wa mikono baada ya uzalishaji.
- `ollama` hutumia kiunganishi cha asili cha HTTP (`/api/chat`) chenye mfano chaguomsingi `qwen3.5:4b`.

## Uzinduzi Uliopendekezwa

Weka usanidi wa awali kuwa mwembamba ili upigaji kura uwe rahisi kuthibitishwa:

1. Anza na iMessage pekee na uthibitishe kuwa `apple-flow service status --json` inaripoti daemon, ufikiaji wa hifadhidata ya Ujumbe, na upigaji kura unaoendelea.
2. Wezesha lango moja la Apple kwa wakati mmoja baada ya upigaji kura kuwa thabiti.
3. Washa Msaidizi, kumbukumbu, ufuatiliaji, na uchunguzi wa mazingira mwishoni.

## Programu ya hiari ya macOS

Programu ya Swift ya onboarding/dashibodi ya ndani imejumuishwa:

- Kifurushi cha programu: `dashboard-app/AppleFlowApp.app`
- Zip inayoweza kusambazwa: `dashboard-app/AppleFlowApp-macOS.zip`

Au jenga/hamisha kutoka nyaraka za chanzo: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Vigezo Chaguomsingi vya Usalama

- Utekelezaji wa orodha nyeupe ya mtumaji
- Vizuizi vya nafasi ya kazi
- Mtiririko wa kazi wa idhini kwa kazi zinazobadilisha
- Uthibitishaji wa mwombaji idhini
- Upungufu wa kiwango
- Ufikiaji wa kusoma tu wa hifadhidata ya iMessage
- Kukandamiza ujumbe unaotoka mara mbili

Maelezo: [SECURITY.md](SECURITY.md)

## Ukaguzi wa Kumbukumbu

Apple Flow sasa inasaidia kumbukumbu ya uchambuzi ya kwanza ya CSV huku ikiendelea kutumia SQLite kama hifadhi ya ukaguzi halali.

- Chanzo halali cha ukaguzi: jedwali la `events` la SQLite (kituo cha `/audit/events`).
- Kioo cha uchambuzi: `agent-office/90_logs/events.csv` (ongeza tu, mstari mmoja kwa tukio).
- Kioo cha Markdown kinachosomeka na binadamu: kimezimwa kwa chaguo-msingi.

Mipangilio inayofaa ya `.env`:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Usimamizi wa Huduma

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Nyaraka

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

## Kuchangia

Angalia [CONTRIBUTING.md](CONTRIBUTING.md).

## Leseni

MIT — angalia [LICENSE](LICENSE).