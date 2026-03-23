<div align="center">

# Apple Flow

**የእርስዎ አፕል ተወላጅ AI ረዳት**

AIን ከiMessage፣ Mail፣ አስታዋሾች፣ ማስታወሻዎች እና የቀን መቁጠሪያ በmacOS ላይ ይቆጣጠሩ።

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

አፕል ፍሎው የአፕል አፕሊኬሽኖችን ከAI CLIዎች (Codex፣ Claude፣ Gemini፣ Cline እና Kilo) ጋር የሚያገናኝ በአገር ውስጥ የሚሰራ macOS daemon ነው። በነባሪነት የአድራሻ ሰጪዎችን የነጭ ዝርዝር፣ ለሚቀይሩ ስራዎች የማጽደቂያ በሮች እና የስራ ቦታ ገደቦችን ያስገድዳል።

## የስክሪንሾቶች

| ዳሽቦርድ | የተግባር አስተዳደር |
|---|---|
| ![Apple Flow ዳሽቦርድ](../docs/screenshots/dashboard.png) | ![Apple Flow የተግባር አስተዳደር](../docs/screenshots/task-management.png) |

| የ AI ፖሊሲ ምዝግብ ማስታወሻ | የቀን መቁጠሪያ ክስተት |
|---|---|
| ![Apple Flow የ AI ፖሊሲ ምዝግብ ማስታወሻ](../docs/screenshots/ai-policy-log.png) | ![Apple Flow የቀን መቁጠሪያ ክስተት](../docs/screenshots/calendar-event.png) |

| የቢሮ አእምሮ ማጎልበት |
|---|
| ![Apple Flow የቢሮ አእምሮ ማጎልበት](../docs/screenshots/office-brainstorm.png) |

### የዳሽቦርድ መተግበሪያ

| መግቢያ 1 | መግቢያ 2 |
|---|---|
| ![Apple Flow የመግቢያ ደረጃ 1](../docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow የመግቢያ ደረጃ 2](../docs/screenshots/onboarding-apple-flow2.png) |

| መግቢያ 3 | መግቢያ 4 |
|---|---|
| ![Apple Flow የመግቢያ ደረጃ 3](../docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow የመግቢያ ደረጃ 4](../docs/screenshots/onboarding-apple-flow4.png) |

| የማዋቀር ቅንብር | የመግቢያ ስህተት |
|---|---|
| ![የአፕል ፍሎው መተግበሪያ የማዋቀር ቅንብር](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![የአፕል ፍሎው የመግቢያ ስህተት ማሳያ](../docs/screenshots/apple-flow-onboarding-error..png) |

## ዋና ዋና ጉዳዮች (ፈጣን ንባብ)

- የአገር ውስጥ መጀመሪያ የአፕል ተወላጅ AI አውቶሜሽን ከጠንካራ የደህንነት ነባሪዎች ጋር (የነጭ ዝርዝር + የማጽደቂያ በሮች + የሥራ ቦታ ገደቦች)።
- በiMessage፣ Mail፣ አስታዋሾች፣ ማስታወሻዎች እና የቀን መቁጠሪያ በኩል በርካታ የመግቢያ በር ስራዎች ከታወቁ የመሳሪያ ፍሰቶች ጋር።
- ከአርታዒ ምልክት (Markdown) ከፍተኛ ጥራት ያለው ሰነድ ለማመንጨት አዲስ የአፕል ገጾች ድጋፍ፣ ገጽታዎችን፣ የይዘት ሰንጠረዦችን፣ ጥቅሶችን፣ ወደ ውጭ መላክን እና ክፍል ዝመናዎችን ጨምሮ።
- ለአዲስ የአፕል ቁጥሮች ድጋፍ ለስራ መጽሐፍ ፈጠራ፣ የሉህ አስተዳደር፣ የረድፍ ማስገቢያ ሴማንቲክስ እና የአጻጻፍ ስልት አውቶሜሽን።
- የኮዴክስ/ክላውድ-ስታይል የስራ ፍሰቶች አለምአቀፍ የክህሎት ጥቅሎች፣ የተወሰኑ `apple-flow-pages`፣ `apple-flow-numbers`፣ `apple-flow-mail` እና `apple-flow-gateways` ክህሎቶችን ጨምሮ።
- የአገልግሎት መቆጣጠሪያዎች፣ የጤና/ሁኔታ መሳሪያዎች እና ሁሉን አቀፍ የሙከራ ሽፋን ጋር ለምርት ዝግጁ የሆኑ ስራዎች።

## ከዚህ ይጀምሩ

አንድ የማዋቀር መንገድ ይምረጡ:

| መንገድ | ለየትኛው ምርጥ ነው | ጊዜ | መግቢያ ነጥብ |
|---|---|---:|---|
| **በኤአይ የሚመራ ማዋቀር (የሚመከር)** | አብዛኛዎቹ ተጠቃሚዎች, በጣም አስተማማኝ የመግቢያ መንገድ | ~10 ደቂቃ | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **አንድ ትእዛዝ ስክሪፕት** | ፈጣን የአገር ውስጥ ጭነት/ራስ-ሰር ማስጀመር | ~5-10 ደቂቃ | `./scripts/setup_autostart.sh` |
| **በእጅ ማዋቀር** | የላቁ/ብጁ አካባቢዎች | ~15+ ደቂቃ | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## ፈጣን ጅምር (በኤአይ የሚመራ)

### 1) ቅድመ ሁኔታዎች

- iMessage የገባበት macOS
- 10 ደቂቃዎች
- Homebrew + Python 3.11 + Node

```bash
# Homebrew ይጫኑ (አስፈላጊ ከሆነ)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python + Node ይጫኑ
brew install python@3.11 node
```

### 2) አንድ የ AI CLI ማገናኛ ይጫኑ

አንዱን ይምረጡ:

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

- Kilo CLI (አማራጭ የላቀ ማገናኛ)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) ክሎን + ቡትስትራፕ

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) በ AI ማስተር ጥያቄ ማዋቀሩን ያጠናቅቁ

የእርስዎን AI CLI ይክፈቱ እና ይለጥፉ:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

ያ ፍሰት የሚከተሉትን ይቆጣጠራል:

- የጤና ምርመራዎች (`wizard doctor --json`)
- ከ`.env.example` የተሟላ `.env` ትውልድ
- ከመጻፍ/ከመጀመር በፊት ግልጽ የማጽደቂያ በሮች
- የመግቢያ በር ሃብት ማዋቀር (አስታዋሾች/ማስታወሻዎች/የቀን መቁጠሪያ)
- ማረጋገጫ + የአገልግሎት ሁኔታ ማረጋገጫ

### 5) ሙሉ የዲስክ መዳረሻ ይስጡ

1. `የስርዓት ቅንብሮች -> ግላዊነት እና ደህንነት -> ሙሉ የዲስክ መዳረሻ`ን ይክፈቱ።
2. Apple Flow የሚጠቀምበትን የPython ሁለትዮሽ ያክሉ (የማዋቀሩ ውጤት መንገዱን ያሳያል)
3. መቀያየሪያውን ያንቁ

### 6) የጭስ ሙከራ

በiMessage እራስዎን ይጻፉ:

```text
what files are in my home directory?
```

በጥቂት ሰከንዶች ውስጥ ምላሽ ማግኘት አለብዎት።

## የማዋቀር መንገዶች (ዝርዝር)

### ሀ) የአንድ ትዕዛዝ ስክሪፕት ብቻ

በኤአይ የሚመራ ማዋቀር ካልፈለጉ:

```bash
./scripts/setup_autostart.sh
```

`.env` ከጠፋ, አንዱን ለመፍጠር `python -m apple_flow setup`ን ያስጀምራል።

### ለ) በእጅ ማዋቀር

`.env`ን በቀጥታ ያርትዑ:

```bash
nano .env
```

ዝቅተኛ ቁልፎች:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

ለአስታዋሾች ላይ ለተመሰረቱ የሥራ ፍሰቶች፣ `apple_flow_reminders_list_name` እና `apple_flow_reminders_archive_list_name` እንደ `agent-task` እና `agent-archive` ያሉ ቀላል ከፍተኛ ደረጃ የዝርዝር ስሞች መሆን አለባቸው። የተከፋፈሉ ዝርዝሮች፣ የተሰበሰቡ ዝርዝሮች፣ የተቆለሉ መንገዶች እና ተደራሽነትን መሰረት ያደረጉ ምትክ አይደገፉም።

ከዚያ ያረጋግጡ እና እንደገና ያስጀምሩ:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## ዋና ትዕዛዞች

| ትእዛዝ | ምን ይሰራል |
|---|---|
| `<ማንኛውም ነገር>` | ተፈጥሯዊ ውይይት |
| `idea: <ጥያቄ>` | የአእምሮ ማጎልበት |
| `plan: <ግብ>` | እቅድ ብቻ (ምንም ለውጦች የሉም) |
| `task: <መመሪያ>` | የሚቀይር ተግባር (ማጽደቅ ያስፈልጋል) |
| `project: <ዝርዝር መግለጫ>` | ባለብዙ ደረጃ ተግባር (ማጽደቅ ያስፈልጋል) |
| `approve <id>` / `deny <id>` / `deny all` | የማጽደቂያ መቆጣጠሪያዎች |
| `status` / `status <run_or_request_id>` | የሩጫ/ጥያቄ ሁኔታ |
| `health` | የዳሞን ጤና |
| `history: [ጥያቄ]` | የመልዕክት ታሪክ |
| `usage` | የአጠቃቀም ስታቲስቲክስ |
| `help` | እገዛ + ተግባራዊ ምክሮች |
| `system: mute` / `system: unmute` | የአጋር መቆጣጠሪያዎች |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | የሩጫ ጊዜ መቆጣጠሪያዎች |
| `system: cancel run <run_id>` | አንድ ሩጫ ይሰርዙ |
| `system: killswitch` | ሁሉንም ንቁ አቅራቢ ሂደቶችን ይገድሉ |

### የብዙ የስራ ቦታ ማዞሪያ

በ`@alias` ቅድመ ቅጥያ:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### ከቅጽል ስሞች ጋር ፋይል ማጣቀሻዎች

በ`.env` ውስጥ የፋይል ቅጽል ስሞችን በ`apple_flow_file_aliases` በኩል ይግለጹ እና በጥያቄዎች ውስጥ በ`@f:<alias>` ይጠቅሷቸው።

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## አማራጭ ውህደቶች

ሁሉም አማራጭ በሮች በነባሪነት ጠፍተዋል።

የቀስቃሽ ባህሪ:

- ነባሪው የቀስቃሽ መለያ `!!agent` ነው።
- ለመልእክት/አስታዋሾች/ማስታወሻዎች/የቀን መቁጠሪያ፣ ያንን መለያ የያዙ ንጥሎች ብቻ ይሰራሉ።
- መለያው ከጥያቄው አፈፃፀም በፊት ይወገዳል።
- በ`apple_flow_trigger_tag` በኩል ያዋቅሩ።

የማንቃት ምሳሌዎች:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

የድምጽ መልዕክት ምሳሌዎች:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

ከዚያም ያንቀሳቅሱ:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` የላኩትን ትክክለኛ ፅሁፍ ይናገራል። `voice-task:` በመጀመሪያ ተግባሩን ያከናውናል፣ ከዚያም የጽሑፍ ውጤቱን እና የተዋሃደ የድምጽ ቅጂን በiMessage በኩል ወደ ተዋቀረው የባለቤት ስልክ ቁጥር ይልካል።

የአጋር + ማህደረ ትውስታ ምሳሌዎች:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Canonical memory v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

የአባሪ ማቀነባበሪያ ምሳሌ:

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

ሲነቃ፣ አፕል ፍሎው የጥያቄ ይዘትን ከiMessage አባሪዎች (የፅሁፍ/ኮድ ፋይሎች፣ ፒዲኤፍዎች፣ ምስሎች በOCR ሲኖሩ፣ የቢሮ ፋይሎች እንደ `.docx/.pptx/.xlsx`፣ እና የድምፅ ማስታወሻዎች በአካባቢያዊ የዊስፐር CLI ግልባጭ) ያወጣል እና ያንን ይዘት በቻት፣ እቅድ ማውጣት እና ማፅደቅ አፈፃፀም ፍሰቶች ውስጥ ያካትታል።

የገቢ iMessage የድምፅ ማስታወሻ ብቻ ከሆነ፣ አፕል ፍሎው አሁን ይገለብጠዋል፣ ወደ ሰው ሰራሽ `voice-task:` ጥያቄ ይለውጠዋል፣ እና በፅሁፍም ሆነ በድምፅ TTS ተከታይ ምላሽ ይሰጣል። `pdftotext` እና `tesseract` ለሌሎች የአባሪ አይነቶች ጥቅም ላይ እንደሚውሉ ሁሉ፣ ለSTT የአካባቢያዊ `whisper` CLI ይጫኑ።

የረዳት ጥገና ምሳሌ:

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

ሲነቃ፣ አፕል ፍሎው በቀላል የጥገና ምርመራ በሰዓት ቆጣሪ ያካሂዳል፣ ደሞን ስራ ፈት ሲሆን የቆዩ ረዳቶችን በቀስታ እንደገና ጥቅም ላይ ያውላል፣ እና የሂደት ክትትል ቴሌሜትሪ በ`health` እና በአድሚን ኤፒአይ በኩል ያሳያል። እንዲሁም `system: recycle helpers` ወይም `system: maintenance` በመጠቀም ተመሳሳይ መንገድን በእጅ ማነሳሳት ይችላሉ።

ሙሉ ቅንብሮችን በ[docs/ENV_SETUP.md](docs/ENV_SETUP.md) ይመልከቱ።

## AI Backend

| አገናኝ | ቁልፍ |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (መሰረታዊ) | `apple_flow_connector=ollama` |

ማስታወሻዎች:

- `codex-cli`፣ `claude-cli` እና `gemini-cli` ሁኔታ የሌላቸው ትዕዛዞችን ያከናውናሉ።
- `cline` ወኪል ነው እና በርካታ አቅራቢዎችን ይደግፋል።
- `kilo-cli` እንደ ማገናኛ የተደገፈ ነው፣ ነገር ግን የማዋቀሪያው ጠንቋይ `generate-env` በአሁኑ ጊዜ `claude-cli`፣ `codex-cli`፣ `gemini-cli`፣ `cline` እና `ollama`ን ያረጋግጣል። ለ`kilo-cli`፣ ማገናኛ መስኮችን ከተፈጠረ በኋላ በእጅ የማዋቀሪያ ጽሑፍ በኩል ያዋቅሩ።
- `ollama` ቤተኛ HTTP ማገናኛን (`/api/chat`) ከነባሪ ሞዴል `qwen3.5:4b` ጋር ይጠቀማል።

## የሚመከር ጅምር

የመጀመሪያውን ማዋቀር ጠባብ ያድርጉት ስለዚህ የድምፅ አሰጣጥን ማረጋገጥ ቀላል እንዲሆን:

1. በiMessage ብቻ ይጀምሩ እና `apple-flow service status --json` ደሞን፣ የመልዕክት ዳታቤዝ መዳረሻ እና ንቁ የድምፅ አሰጣጥን ሪፖርት ማድረጉን ያረጋግጡ።
2. የድምፅ አሰጣጥ የተረጋጋ ከሆነ በኋላ አንድ በአንድ የአፕል መግቢያ በርን ያንቁ።
3. ረዳትን፣ ማህደረ ትውስታን፣ ተከታይ ተግባራትን እና የአካባቢ ቅኝትን በመጨረሻ ያንቁ።

## አማራጭ የmacOS መተግበሪያ

አንድ የSwift ኦንቦርዲንግ/ዳሽቦርድ መተግበሪያ ተካትቷል:

- የመተግበሪያ ጥቅል: `dashboard-app/AppleFlowApp.app`
- ሊሰራጭ የሚችል ዚፕ: `dashboard-app/AppleFlowApp-macOS.zip`

ወይም ከምንጭ ሰነዶች ይገንቡ/ወደ ውጭ ይላኩ: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## የደህንነት ነባሪዎች

- የአድራሻ ሰጪ የነጭ ዝርዝር ማስፈጸሚያ
- የስራ ቦታ ገደቦች
- ለሚቀይሩ ተግባራት የማጽደቂያ የስራ ፍሰት
- የአጽዳቂው አድራሻ ሰጪ ማረጋገጫ
- የፍጥነት ገደብ
- iMessage DB የመዳረሻ ንባብ-ብቻ
- የተባዙ የወጪ መልዕክቶችን ማፈን

ዝርዝሮች: [SECURITY.md](SECURITY.md)

## የኦዲት ምዝገባ

አፕል ፍሎው አሁን SQLiteን እንደ ቀኖናዊ የኦዲት ማከማቻ እየያዘ የCSV-መጀመሪያ ትንተና ምዝግብ ማስታወሻን ይደግፋል።

- ቀኖናዊ የኦዲት ምንጭ: SQLite `events` ሰንጠረዥ (`/audit/events` መጨረሻ ነጥብ)።
- የትንተና መስታወት: `agent-office/90_logs/events.csv` (መጨመር ብቻ, ለእያንዳንዱ ክስተት አንድ ረድፍ)።
- በሰው የሚነበብ የማርክዳውን መስታወት: በነባሪነት ተሰናክሏል።

ተዛማጅ `.env` ቅንብሮች:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## የአገልግሎት አስተዳደር

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## ሰነዶች

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

## አስተዋጽዖ ማድረግ

[CONTRIBUTING.md](CONTRIBUTING.md)ን ይመልከቱ።

## ፍቃድ

MIT — [LICENSE](LICENSE]ን ይመልከቱ።