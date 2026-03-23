<div align="center">

# Apple Flow

**Mataimakin AI ɗinku na asali na Apple**

Kula da AI daga iMessage, Mail, Tunatarwa, Bayanan kula, da Kalanda akan macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow wani daemon ne na macOS mai fifita na gida, wanda ke haɗa aikace-aikacen Apple zuwa CLI na AI (Codex, Claude, Gemini, Cline, da Kilo). Yana aiwatar da farar-fata na masu aikawa, ƙofofin yarda don ayyukan da ke canzawa, da ƙuntatawa na wurin aiki ta hanyar tsoho.

## Hotunan allo

| Dashboard | Gudanar da Ayyuka |
|---|---|
| ![Apple Flow dashboard](../docs/screenshots/dashboard.png) | ![Gudanar da Ayyuka na Apple Flow](../docs/screenshots/task-management.png) |

| Rajistar Siyasa ta AI | Taron Kalanda |
|---|---|
| ![Rajistar Siyasa ta AI na Apple Flow](../docs/screenshots/ai-policy-log.png) | ![Taron Kalanda na Apple Flow](../docs/screenshots/calendar-event.png) |

| Zuga-zugar Ofis |
|---|
| ![Zuga-zugar Ofis na Apple Flow](../docs/screenshots/office-brainstorm.png) |

### Aikace-aikacen Dashboard

| Shigarwa 1 | Shigarwa 2 |
|---|---|
| ![Apple Flow matakin shigarwa na 1](../docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow matakin shigarwa na 2](../docs/screenshots/onboarding-apple-flow2.png) |

| Shigarwa 3 | Shigarwa 4 |
|---|---|
| ![Apple Flow matakin shigarwa na 3](../docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow matakin shigarwa na 4](../docs/screenshots/onboarding-apple-flow4.png) |

| Saituwar Sati | Kuskuren Shigarwa |
|---|---|
| ![Saituwar sati na aikace-aikacen Apple Flow](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Kuskuren shigarwa na Apple Flow](../docs/screenshots/apple-flow-onboarding-error..png) |

## Abubuwan ban mamaki (Karatu na Gaggawa)

- Tsarin sarrafa AI na Apple na asali, mai fifita na gida, tare da ƙa'idodin tsaro masu ƙarfi (farar-fata + ƙofofin yarda + iyakokin wurin aiki).
- Ayyukan ƙofa da yawa ta hanyar iMessage, Mail, Tunatarwa, Bayanan kula, da Kalanda tare da tabbataccen kwararar kayan aiki.
- Sabon tallafi na Apple Pages don ƙirƙirar takardu masu inganci daga Markdown, gami da jigogi, teburin abubuwan ciki, ambato, fitarwa, da sabunta sassa.
- Sabon tallafi na Apple Numbers don ƙirƙirar littattafan aiki, gudanar da takardu, ma'anar shigar da layi, da sarrafa salo.
- Fakitin basira na duniya don ayyukan salon Codex/Claude, gami da basira na musamman `apple-flow-pages`, `apple-flow-numbers`, `apple-flow-mail`, da `apple-flow-gateways`.
- Ayyukan da aka shirya don samarwa tare da sarrafa sabis, kayan aikin lafiya/hali, da cikakken ɗaukar gwaji.

## Fara nan

Zabi hanya ɗaya ta saitawa:

| Hanya | Mafi kyau ga | Lokaci | Abun shiga |
|---|---|---:|---|
| **Saitawa da AI ke jagoranta (shawarar)** | Yawancin masu amfani, mafi aminci shigarwa | ~10 min | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Rubutun umarni guda ɗaya** | Saurin shigarwa na gida/autostart | ~5-10 min | `./scripts/setup_autostart.sh` |
| **Saitawa na hannu** | Yanayi masu ci gaba/custom | ~15+ min | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Fara Gaggawa (AI-jagora)

### 1) Abubuwan da ake bukata

- macOS tare da iMessage shiga
- Minti 10
- Homebrew + Python 3.11 + Node

```bash
# Sanya Homebrew (idan an buƙata)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Sanya Python + Node
brew install python@3.11 node
```

### 2) Sanya Haɗin AI CLI Daya

Zabi daya:

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

- Kilo CLI (ƙarin haɗin gwiwa na zaɓi)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Kwafa + Fara

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Kammala Saituwa da AI Master Prompt

Bude AI CLI dinka ka liƙa:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Wannan kwarara tana kula da:

- Duban lafiya (`wizard doctor --json`)
- Cikakken ƙirƙirar `.env` daga `.env.example`
- Ƙofofin tabbatarwa na bayyane kafin rubutu/sake kunnawa
- Saituwar albarkatun ƙofa (Tunatarwa/Bayanan kula/Kalanda)
- Tabbatarwa + tabbatarwar halin sabis

### 5) Bada Damar Cikakken Faifai

1. Bude `Saitunan Tsarin -> Sirri & Tsaro -> Cikakken Faifai`
2. Ƙara binary na Python da Apple Flow ke amfani da shi (fitarwa saitawa yana nuna hanya)
3. Kunna sauyawa

### 6) Gwajin Hayaki

Aikawa kanka a iMessage:

```text
what files are in my home directory?
```

Ya kamata ka sami amsa cikin 'yan dakikoki.

## Hanyoyin Saitawa (Cikakkun bayanai)

### A) Rubutun umarni guda ɗaya kawai

Idan ba ka so saiti mai jagorancin AI:

```bash
./scripts/setup_autostart.sh
```

Idan `.env` ya ɓace, zai kaddamar da `python -m apple_flow setup` don ƙirƙirar ɗaya.

### B) Saitawa na hannu

Gyara `.env` kai tsaye:

```bash
nano .env
```

Maɓallan mafi ƙaranci:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Domin ayyukan da suke da alaka da Tunatarwa, `apple_flow_reminders_list_name` da `apple_flow_reminders_archive_list_name` dole ne su kasance sunaye masu sauki na sama kamar `agent-task` da `agent-archive`. Ba a tallafa wa jerin abubuwan da aka raba, jerin abubuwan da aka haɗa, hanyoyin da aka saka, da kuma hanyoyin da aka maye gurbi da aka dogara da damar shiga.

Sa'an nan tabbatar da sake kunnawa:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Mahimman Umarni

| Umarni | Abinda yake yi |
|---|---|
| `<kowane abu>` | Hira ta halitta |
| `idea: <shawara>` | Zuga-zuga |
| `plan: <manufa>` | Tsari kawai (babu canje-canje) |
| `task: <umarni>` | Aikin canzawa (ana buƙatar yarda) |
| `project: <sipesifikesonu>` | Aikin mataki da yawa (ana buƙatar yarda) |
| `approve <id>` / `deny <id>` / `deny all` | Sarrafa yarda |
| `status` / `status <run_or_request_id>` | Halin gudu/buƙata |
| `health` | Lafiyar Daemon |
| `history: [tambaya]` | Tarihin saƙo |
| `usage` | Ƙididdigar amfani |
| `help` | Taimako + shawarwari masu amfani |
| `system: mute` / `system: unmute` | Sarrafa aboki |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Sarrafa lokacin aiki |
| `system: cancel run <run_id>` | Soke gudu ɗaya |
| `system: killswitch` | Kashe duk wani aikin mai bada sabis |

### Sarrafa hanyar aiki da yawa

Yi prefix da `@alias`:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Abubuwan da aka ambata na fayil tare da alias

Bayyana alias na fayil a cikin `.env` ta hanyar `apple_flow_file_aliases` kuma koma zuwa gare su a cikin prompts tare da `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Haɗin gwiwar Zaɓi

Duk ƙofofin zaɓi an kashe su ta hanyar tsoho.

Halayen mai kunnawa:

- Alamar mai kunnawa ta tsoho ita ce `!!agent`
- Ga Mail/Tunatarwa/Bayanan kula/Kalanda, abubuwan da ke ɗauke da wannan alamar kawai za a sarrafa su
- Alamar tana cirewa kafin aiwatar da tambaya
- Saita ta hanyar `apple_flow_trigger_tag`

Misalai na kunnawa:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Misalai na saƙonnin murya:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Sa'an nan kunna tare da:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` yana magana da ainihin rubutun da kuka aika. `voice-task:` yana fara aikin, sannan yana aika duka sakamakon rubutun da kwafin sauti da aka haɗa ta hanyar iMessage zuwa lambar mai mallaka da aka saita.

Misalai na aboki + ƙwaƙwalwar ajiya:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Canonical memory v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Misali na sarrafa haɗe-haɗe:

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

Lokacin da aka kunna, Apple Flow yana fitar da mahallin tambaya daga abubuwan da aka haɗa na iMessage (fayilolin rubutu/code, PDF, hotuna ta hanyar OCR idan akwai, fayilolin Office kamar `.docx/.pptx/.xlsx`, da saƙonnin murya ta hanyar Whisper CLI na gida) kuma ya haɗa wannan mahallin a cikin hira, shiryawa, da kuma aiwatar da yarda.

Idan iMessage mai shigowa kawai memo ce ta murya, Apple Flow yanzu zai rubuta ta, ya canza ta zuwa buƙatar `voice-task:` ta roba, kuma ya amsa duka da rubutu da kuma biyo baya na TTS da aka faɗa. Sanya `whisper` CLI na gida don STT, kamar yadda ake amfani da `pdftotext` da `tesseract` don wasu nau'ikan haɗe-haɗe.

Misalin kiyaye mataimaki:

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

Lokacin da aka kunna, Apple Flow yana gudanar da dubawa mai sauƙi na kulawa akan mai ƙidayar lokaci, yana sake sarrafa masu taimakawa da aka tsufa a hankali lokacin da daemon ke aiki, kuma yana fallasa telemetry na mai lura da ci gaba ta hanyar `health` da API na admin. Hakanan zaka iya kunna hanya ɗaya da hannu tare da `system: recycle helpers` ko `system: maintenance`.

Duba cikakkun saituna a [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## Bayanan baya na AI

| Haɗin | Maɓalli |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (na asali) | `apple_flow_connector=ollama` |

Lura:

- `codex-cli`, `claude-cli`, da `gemini-cli` suna gudanar da umarni marasa jihohi.
- `cline` wakili ne kuma yana tallafawa masu bada sabis da yawa.
- `kilo-cli` ana tallafa masa a matsayin mai haɗawa, amma mai siyarwa na saitawa `generate-env` a halin yanzu yana tabbatar da `claude-cli`, `codex-cli`, `gemini-cli`, `cline`, da `ollama`. Don `kilo-cli`, saita filayen mai haɗawa ta hanyar rubutun saitawa na hannu bayan samarwa.
- `ollama` yana amfani da na'ura mai haɗawa ta HTTP (`/api/chat`) tare da ƙirar asali `qwen3.5:4b`.

## Farkon Farawa da Aka Ba da Shawara

Ka kiyaye saitunan farko a takaitacce domin a iya tabbatar da zaɓe cikin sauƙi:

1. Fara da iMessage kawai kuma tabbatar cewa `apple-flow service status --json` yana bada rahoto game da daemon, damar shiga DB na saƙonni, da kuma zaɓe mai aiki.
2. Kunna kowace kofa ta Apple ɗaya bayan an tabbatar da zaɓen.
3. Kunna Aboki, ƙwaƙwalwar ajiya, bin diddigi, da kuma bincike na muhalli a ƙarshe.

## Aikace-aikacen macOS na zaɓi

An haɗa aikace-aikacen shigarwa/dashboard na Swift na gida:

- Fakitin aikace-aikace: `dashboard-app/AppleFlowApp.app`
- Zip da za a iya rarrabawa: `dashboard-app/AppleFlowApp-macOS.zip`

Ko kuma gina/fitarwa daga takaddun tushe: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Tsarin Tsaro na Tsoho

- Aiwatar da farar-fata na mai aikawa
- Ƙuntatawa na wurin aiki
- Aikin yarda don ayyukan canzawa
- Tabbatar da mai neman yarda
- Iyakance gudun
- Damar karatu kawai zuwa DB na iMessage
- Hana fitarwa biyu

Cikakkun bayanai: [SECURITY.md](SECURITY.md)

## Rajistar Bincike

Apple Flow yanzu yana tallafawa log ɗin bincike na farko na CSV yayin da yake riƙe SQLite a matsayin kantin bincike na canonical.

- Tushen bincike na Canonical: teburin `events` na SQLite (mafi ƙarshe `/audit/events`).
- Madubi na bincike: `agent-office/90_logs/events.csv` (ƙarawa kawai, layi ɗaya ga kowane taron).
- Madubi na Markdown mai karantawa ga ɗan adam: an kashe shi ta hanyar tsoho.

Saitunan `.env` masu dacewa:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Gudanar da Sabis

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Takaddun Shaida

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

## Bayar da Gudunmawa

Duba [CONTRIBUTING.md](CONTRIBUTING.md).

## Lasisi

MIT — duba [LICENSE](LICENSE).