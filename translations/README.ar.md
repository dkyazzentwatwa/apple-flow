<div align="center">

# Apple Flow

**مساعدك الذكي الأصيل من Apple**

تحكم في الذكاء الاصطناعي من خلال iMessage، والبريد، والتذكيرات، والملاحظات، والتقويم على نظام macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow هو برنامج خفي (daemon) يعمل على نظام macOS، ويفضل العمل المحلي أولاً، ويربط تطبيقات Apple بواجهات سطر الأوامر الخاصة بالذكاء الاصطناعي (Codex، Claude، Gemini، Cline، و Kilo). يفرض بشكل افتراضي قوائم بيضاء للمرسلين، وبوابات موافقة للأعمال التي تتطلب تعديلاً، وقيودًا على مساحة العمل.

## لقطات الشاشة

| لوحة التحكم | إدارة المهام |
|---|---|
| ![لوحة تحكم Apple Flow](../docs/screenshots/dashboard.png) | ![إدارة المهام في Apple Flow](../docs/screenshots/task-management.png) |

| سجل سياسة الذكاء الاصطناعي | حدث التقويم |
|---|---|
| ![سجل سياسة الذكاء الاصطناعي في Apple Flow](../docs/screenshots/ai-policy-log.png) | ![حدث التقويم في Apple Flow](../docs/screenshots/calendar-event.png) |

| عصف ذهني مكتبي |
|---|
| ![عصف ذهني مكتبي في Apple Flow](../docs/screenshots/office-brainstorm.png) |

### تطبيق لوحة التحكم

| الإعداد الأولي 1 | الإعداد الأولي 2 |
|---|---|
| ![الخطوة 1 من الإعداد الأولي لـ Apple Flow](../docs/screenshots/onboarding-apple-flow1.png) | ![الخطوة 2 من الإعداد الأولي لـ Apple Flow](../docs/screenshots/onboarding-apple-flow2.png) |

| الإعداد الأولي 3 | الإعداد الأولي 4 |
|---|---|
| ![الخطوة 3 من الإعداد الأولي لـ Apple Flow](../docs/screenshots/onboarding-apple-flow3.png) | ![الخطوة 4 من الإعداد الأولي لـ Apple Flow](../docs/screenshots/onboarding-apple-flow4.png) |

| تكوين الإعداد | خطأ الإعداد الأولي |
|---|---|
| ![تكوين إعداد تطبيق Apple Flow](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![شاشة خطأ الإعداد الأولي لتطبيق Apple Flow](../docs/screenshots/apple-flow-onboarding-error..png) |

## النقاط البارزة (قراءة سريعة)

- أتمتة ذكاء اصطناعي أصيلة من Apple، تفضل العمل المحلي أولاً، مع افتراضات أمان قوية (قائمة بيضاء + بوابات موافقة + حدود مساحة العمل).
- عمليات متعددة البوابات عبر iMessage، والبريد، والتذكيرات، والملاحظات، والتقويم مع تدفقات أدوات محددة.
- دعم جديد لـ Apple Pages لإنشاء مستندات عالية الجودة من Markdown، بما في ذلك السمات، وجداول المحتويات، والمراجع، والتصدير، وتحديثات الأقسام.
- دعم جديد لـ Apple Numbers لإنشاء المصنفات، وإدارة الأوراق، ودلالات إدراج الصفوف، وأتمتة الأنماط.
- حزم مهارات عالمية لسير العمل بأسلوب Codex/Claude، بما في ذلك مهارات `apple-flow-pages`، و`apple-flow-numbers`، و`apple-flow-mail`، و`apple-flow-gateways` المخصصة.
- عمليات جاهزة للإنتاج مع عناصر تحكم الخدمة، وأدوات الصحة/الحالة، وتغطية شاملة للاختبارات.

## ابدأ هنا

اختر مسار إعداد واحد:

| المسار | الأفضل لـ | الوقت | نقطة الدخول |
|---|---|---:|---|
| **الإعداد الموجه بالذكاء الاصطناعي (موصى به)** | معظم المستخدمين، الترحيب الأكثر أمانًا | ~10 دقائق | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **برنامج نصي بامر واحد** | تثبيت محلي/بدء تلقائي سريع | ~5-10 دقائق | `./scripts/setup_autostart.sh` |
| **الإعداد اليدوي** | بيئات متقدمة/مخصصة | ~15+ دقيقة | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md)، [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## البدء السريع (موجه بالذكاء الاصطناعي)

### 1) المتطلبات الأساسية

- macOS مع تسجيل الدخول إلى iMessage
- 10 دقائق
- Homebrew + Python 3.11 + Node

```bash
# تثبيت Homebrew (إذا لزم الأمر)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# تثبيت Python + Node
brew install python@3.11 node
```

### 2) تثبيت موصل واحد لواجهة سطر الأوامر للذكاء الاصطناعي

اختر واحدًا:

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

- Kilo CLI (موصل متقدم اختياري)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) استنساخ + تمهيد

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) إنهاء التكوين باستخدام المطالبة الرئيسية للذكاء الاصطناعي

افتح واجهة سطر الأوامر الخاصة بالذكاء الاصطناعي والصق:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

يتعامل هذا التدفق مع:

- فحوصات السلامة (`wizard doctor --json`)
- إنشاء ملف `.env` بالكامل من ملف `.env.example`
- بوابات تأكيد صريحة قبل عمليات الكتابة/إعادة التشغيل
- إعداد موارد البوابة (التذكيرات/الملاحظات/التقويم)
- التحقق من الصحة + التحقق من حالة الخدمة

### 5) منح وصول كامل إلى القرص

1. افتح `إعدادات النظام -> الخصوصية والأمان -> وصول كامل إلى القرص`
2. أضف الثنائي الخاص بلغة Python الذي يستخدمه Apple Flow (تعرض مخرجات الإعداد المسار)
3. قم بتمكين التبديل

### 6) اختبار الدخان

أرسل رسالة نصية إلى نفسك في iMessage:

```text
what files are in my home directory?
```

يجب أن تتلقى ردًا في غضون ثوانٍ.

## مسارات الإعداد (مفصلة)

### أ) برنامج نصي بامر واحد فقط

إذا كنت لا ترغب في الإعداد الموجه بالذكاء الاصطناعي:

```bash
./scripts/setup_autostart.sh
```

إذا كان ملف `.env` مفقودًا، فإنه يطلق `python -m apple_flow setup` لإنشاء واحد.

### ب) الإعداد اليدوي

عدّل ملف `.env` مباشرةً:

```bash
nano .env
```

الحد الأدنى من المفاتيح:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

بالنسبة لسير العمل المدعوم بالتذكيرات، يجب أن تكون `apple_flow_reminders_list_name` و`apple_flow_reminders_archive_list_name` أسماء قوائم بسيطة على المستوى الأعلى مثل `agent-task` و`agent-archive`. لا يتم دعم القوائم المقسمة والقوائم المجمعة والمسارات المتداخلة والبدائل المدعومة بإمكانية الوصول.

ثم تحقق وأعد التشغيل:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## الأوامر الأساسية

| الأمر | ماذا يفعل |
|---|---|
| `<أي شيء>` | دردشة طبيعية |
| `idea: <مطالبة>` | عصف ذهني |
| `plan: <هدف>` | خطة فقط (لا توجد تغييرات) |
| `task: <تعليمات>` | مهمة تتطلب تعديلًا (تتطلب موافقة) |
| `project: <مواصفات>` | مهمة متعددة الخطوات (تتطلب موافقة) |
| `approve <معرف>` / `deny <معرف>` / `deny all` | عناصر التحكم بالموافقة |
| `status` / `status <معرف_تشغيل_أو_طلب>` | حالة التشغيل/الطلب |
| `health` | صحة البرنامج الخفي |
| `history: [استعلام]` | سجل الرسائل |
| `usage` | إحصائيات الاستخدام |
| `help` | مساعدة + نصائح عملية |
| `system: mute` / `system: unmute` | عناصر التحكم في الرفيق |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | عناصر التحكم في وقت التشغيل |
| `system: cancel run <معرف_التشغيل>` | إلغاء تشغيل واحد |
| `system: killswitch` | إيقاف جميع عمليات الموفر النشطة |

### توجيه مساحات عمل متعددة

بادئة بـ `@alias`:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### مراجع الملفات باستخدام الأسماء المستعارة

قم بتعريف الأسماء المستعارة للملفات في ملف `.env` عبر `apple_flow_file_aliases` وارجع إليها في المطالبات باستخدام `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## عمليات التكامل الاختيارية

جميع البوابات الاختيارية معطلة افتراضيًا.

سلوك المشغل:

- علامة المشغل الافتراضية هي `!!agent`
- بالنسبة للبريد/التذكيرات/الملاحظات/التقويم، يتم معالجة العناصر التي تحتوي على هذه العلامة فقط
- يتم تجريد العلامة قبل تنفيذ المطالبة
- التكوين عبر `apple_flow_trigger_tag`

أمثلة التمكين:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

أمثلة الرسائل الصوتية:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

ثم قم بالتشغيل باستخدام:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` ينطق النص الدقيق الذي ترسله. `voice-task:` يقوم أولاً بتشغيل المهمة، ثم يرسل كلاً من نتيجة النص ونسخة صوتية مركبة عبر iMessage إلى رقم المالك المكون.

أمثلة الرفيق + الذاكرة:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# الذاكرة الأساسية v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

مثال معالجة المرفقات:

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

عند التمكين، يستخرج Apple Flow سياق المطالبة من مرفقات iMessage (ملفات النصوص/التعليمات البرمجية، ملفات PDF، الصور عبر OCR عند توفرها، ملفات Office مثل `.docx/.pptx/.xlsx`، ومذكرات الصوت عبر تحويل الصوت إلى نص باستخدام Whisper CLI المحلي) ويتضمن هذا السياق في تدفقات الدردشة والتخطيط وتنفيذ الموافقة.

إذا كانت رسالة iMessage الواردة مجرد ملاحظة صوتية، يقوم Apple Flow الآن بنسخها، وتحويلها إلى طلب `voice-task:` اصطناعي، والرد بكل من النص ومتابعة TTS منطوقة. قم بتثبيت واجهة سطر أوامر `whisper` محلية لتحويل الصوت إلى نص، على غرار كيفية استخدام `pdftotext` و`tesseract` لأنواع المرفقات الأخرى.

مثال صيانة المساعد:

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

عند التمكين، يقوم Apple Flow بإجراء فحص صيانة خفيف الوزن على مؤقت، ويعيد تدوير المساعدين القدماء بلطف عندما يكون البرنامج الخفي خاملاً، ويعرض قياسات المراقبة التقدمية عبر `health` وواجهة برمجة تطبيقات المسؤول. يمكنك أيضًا تشغيل نفس المسار يدويًا باستخدام `system: recycle helpers` أو `system: maintenance`.

انظر الإعدادات الكاملة في [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## واجهات الذكاء الاصطناعي الخلفية

| الموصل | المفتاح |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (أصلي) | `apple_flow_connector=ollama` |

ملاحظات:

- `codex-cli` و`claude-cli` و`gemini-cli` تنفذ أوامر لا حالة لها.
- `cline` عامل ويقدم دعمًا للعديد من الموفرين.
- `kilo-cli` مدعوم كموصل، ولكن معالج الإعداد `generate-env` يتحقق حاليًا من `claude-cli` و`codex-cli` و`gemini-cli` و`cline` و`ollama`. بالنسبة لـ `kilo-cli`، قم بتعيين حقول الموصل عبر كتابة التكوين اليدوية بعد الإنشاء.
- `ollama` يستخدم موصل HTTP أصلي (`/api/chat`) مع النموذج الافتراضي `qwen3.5:4b`.

## البدء الموصى به

حافظ على إعداد أولي ضيق بحيث يكون التحقق من الاستطلاع سهلاً:

1. ابدأ بـ iMessage فقط وتأكد من أن `apple-flow service status --json` يشير إلى البرنامج الخفي والوصول إلى قاعدة بيانات الرسائل والاستطلاع النشط.
2. قم بتمكين بوابة Apple واحدة في كل مرة بعد استقرار الاستطلاع.
3. قم بتشغيل الرفيق والذاكرة والمتابعات والمسح المحيطي أخيرًا.

## تطبيق macOS الاختياري

يتم تجميع تطبيق لوحة معلومات/ترحيب Swift محلي:

- حزمة التطبيق: `dashboard-app/AppleFlowApp.app`
- ملف مضغوط قابل للتوزيع: `dashboard-app/AppleFlowApp-macOS.zip`

أو قم بالبناء/التصدير من وثائق المصدر: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## الإعدادات الافتراضية للأمان

- فرض قائمة بيضاء للمرسلين
- قيود مساحة العمل
- سير عمل الموافقة للمهام التي تتطلب تعديلاً
- التحقق من طالب الموافقة
- تحديد المعدل
- وصول للقراءة فقط إلى قاعدة بيانات iMessage
- قمع المخرجات المكررة

التفاصيل: [SECURITY.md](SECURITY.md)

## سجلات التدقيق

يدعم Apple Flow الآن سجل تحليلات بتنسيق CSV أولاً مع الاحتفاظ بـ SQLite كمتجر تدقيق قانوني.

- مصدر التدقيق القانوني: جدول `events` في SQLite (نقطة نهاية `/audit/events`).
- مرآة التحليلات: `agent-office/90_logs/events.csv` (إضافة فقط، سطر واحد لكل حدث).
- مرآة Markdown قابلة للقراءة البشرية: معطلة افتراضيًا.

إعدادات `.env` ذات الصلة:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## إدارة الخدمات

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## التوثيق

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

## المساهمة

انظر [CONTRIBUTING.md](CONTRIBUTING.md).

## الترخيص

MIT — انظر [LICENSE](LICENSE).