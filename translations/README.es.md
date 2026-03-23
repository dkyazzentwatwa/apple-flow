<div align="center">

# Apple Flow

**Tu Asistente de IA nativo de Apple**

Controla la IA desde iMessage, Mail, Recordatorios, Notas y Calendario en macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow es un demonio de macOS local que conecta las aplicaciones de Apple a las CLI de IA (Codex, Claude, Gemini, Cline y Kilo). Aplica listas de remitentes permitidos, puertas de aprobación para trabajos que modifican el sistema y restricciones de espacio de trabajo por defecto.

## Capturas de pantalla

| Panel de control | Gestión de tareas |
|---|---|
| ![Panel de control de Apple Flow](../docs/screenshots/dashboard.png) | ![Gestión de tareas de Apple Flow](../docs/screenshots/task-management.png) |

| Registro de política de IA | Evento del calendario |
|---|---|
| ![Registro de política de IA de Apple Flow](../docs/screenshots/ai-policy-log.png) | ![Evento del calendario de Apple Flow](../docs/screenshots/calendar-event.png) |

| Lluvia de ideas en la oficina |
|---|
| ![Lluvia de ideas en la oficina de Apple Flow](../docs/screenshots/office-brainstorm.png) |

### Aplicación de panel de control

| Incorporación 1 | Incorporación 2 |
|---|---|
| ![Paso 1 de incorporación de Apple Flow](../docs/screenshots/onboarding-apple-flow1.png) | ![Paso 2 de incorporación de Apple Flow](../docs/screenshots/onboarding-apple-flow2.png) |

| Incorporación 3 | Incorporación 4 |
|---|---|
| ![Paso 3 de incorporación de Apple Flow](../docs/screenshots/onboarding-apple-flow3.png) | ![Paso 4 de incorporación de Apple Flow](../docs/screenshots/onboarding-apple-flow4.png) |

| Configuración de la instalación | Error de incorporación |
|---|---|
| ![Configuración de la instalación de la aplicación Apple Flow](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Pantalla de error de incorporación de Apple Flow](../docs/screenshots/apple-flow-onboarding-error..png) |

## Destacados (lectura rápida)

- Automatización de IA nativa de Apple, con prioridad local y fuertes valores predeterminados de seguridad (lista de permitidos + puertas de aprobación + límites de espacio de trabajo).
- Operaciones multigates a través de iMessage, Mail, Recordatorios, Notas y Calendario con flujos de herramientas deterministas.
- Nuevo soporte para Apple Pages para la generación de documentos de alta calidad a partir de Markdown, incluyendo temas, tablas de contenido, citas, exportaciones y actualizaciones de secciones.
- Nuevo soporte para Apple Numbers para la creación de libros de trabajo, gestión de hojas, semántica de inserción de filas y automatización de estilos.
- Paquetes de habilidades globales para flujos de trabajo estilo Codex/Claude, incluyendo habilidades dedicadas a `apple-flow-pages`, `apple-flow-numbers`, `apple-flow-mail` y `apple-flow-gateways`.
- Operaciones listas para producción con controles de servicio, herramientas de salud/estado y cobertura de pruebas completa.

## Comienza aquí

Elige una ruta de configuración:

| Ruta | Mejor para | Tiempo | Punto de entrada |
|---|---|---:|---|
| **Configuración guiada por IA (recomendado)** | La mayoría de los usuarios, la incorporación más segura | ~10 min | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Script de un comando** | Instalación local/inicio automático rápido | ~5-10 min | `./scripts/setup_autostart.sh` |
| **Configuración manual** | Entornos avanzados/personalizados | ~15+ min | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Inicio rápido (guiado por IA)

### 1) Prerrequisitos

- macOS con iMessage iniciado sesión
- 10 minutos
- Homebrew + Python 3.11 + Node

```bash
# Instalar Homebrew (si es necesario)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Instalar Python + Node
brew install python@3.11 node
```

### 2) Instalar un conector de IA CLI

Elige uno:

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

- Kilo CLI (conector avanzado opcional)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Clonar + Arrancar

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Finalizar la configuración con el Prompt Maestro de IA

Abre tu CLI de IA y pega:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Ese flujo maneja:

- Comprobaciones de salud (`wizard doctor --json`)
- Generación completa de `.env` desde `.env.example`
- Puertas de confirmación explícitas antes de escrituras/reinicios
- Configuración de recursos de pasarela (Recordatorios/Notas/Calendario)
- Validación + verificación del estado del servicio

### 5) Conceder acceso total al disco

1. Abre `Ajustes del Sistema -> Privacidad y seguridad -> Acceso total al disco`
2. Añade el binario de Python utilizado por Apple Flow (la salida de la configuración muestra la ruta)
3. Habilita el interruptor

### 6) Prueba de humo

Envía un mensaje a ti mismo en iMessage:

```text
what files are in my home directory?
```

Deberías recibir una respuesta en segundos.

## Rutas de configuración (detalladas)

### A) Solo script de un comando

Si no quieres la configuración guiada por IA:

```bash
./scripts/setup_autostart.sh
```

Si falta `.env`, lanza `python -m apple_flow setup` para generar uno.

### B) Configuración manual

Edita `.env` directamente:

```bash
nano .env
```

Claves mínimas:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Para flujos de trabajo basados en Recordatorios, `apple_flow_reminders_list_name` y `apple_flow_reminders_archive_list_name` deben ser nombres de listas de nivel superior simples como `agent-task` y `agent-archive`. Las listas seccionadas, las listas agrupadas, las rutas anidadas y las alternativas basadas en la accesibilidad no son compatibles.

Luego valida y reinicia:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Comandos principales

| Comando | Qué hace |
|---|---|
| `<anything>` | Chat natural |
| `idea: <prompt>` | Lluvia de ideas |
| `plan: <goal>` | Solo plan (sin cambios) |
| `task: <instruction>` | Tarea de modificación (se requiere aprobación) |
| `project: <spec>` | Tarea de varios pasos (se requiere aprobación) |
| `approve <id>` / `deny <id>` / `deny all` | Controles de aprobación |
| `status` / `status <run_or_request_id>` | Estado de ejecución/solicitud |
| `health` | Salud del demonio |
| `history: [query]` | Historial de mensajes |
| `usage` | Estadísticas de uso |
| `help` | Ayuda + consejos prácticos |
| `system: mute` / `system: unmute` | Controles del compañero |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Controles de tiempo de ejecución |
| `system: cancel run <run_id>` | Cancelar una ejecución |
| `system: killswitch` | Detener todos los procesos de proveedor activos |

### Enrutamiento multi-espacio de trabajo

Prefija con `@alias`:

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Referencias de archivos con alias

Define alias de archivos en `.env` a través de `apple_flow_file_aliases` y reférencialos en los prompts con `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Integraciones opcionales

Todas las pasarelas opcionales están desactivadas por defecto.

Comportamiento del disparador:

- La etiqueta de disparo predeterminada es `!!agent`
- Para Mail/Recordatorios/Notas/Calendario, solo se procesan los elementos que contienen esa etiqueta
- La etiqueta se elimina antes de la ejecución del prompt
- Configura a través de `apple_flow_trigger_tag`

Ejemplos de habilitación:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Ejemplos de mensajes de voz:

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Luego dispara con:

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` pronuncia el texto exacto que envías. `voice-task:` ejecuta la tarea primero, luego envía el resultado del texto y una copia de audio sintetizada a través de iMessage al número de propietario configurado.

Ejemplos de compañero + memoria:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Memoria canónica v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Ejemplo de procesamiento de adjuntos:

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

Cuando está habilitado, Apple Flow extrae el contexto del prompt de los adjuntos de iMessage (archivos de texto/código, PDF, imágenes a través de OCR cuando estén disponibles, archivos de Office como `.docx/.pptx/.xlsx` y notas de voz de audio a través de la transcripción de la CLI de Whisper local) e incluye ese contexto en los flujos de chat, planificación y ejecución de aprobación.

Si un iMessage entrante es solo una nota de voz, Apple Flow ahora la transcribe, la convierte en una solicitud `voice-task:` sintética y responde con el texto y un seguimiento de TTS hablado. Instala una CLI local de `whisper` para STT, de forma similar a cómo se usan `pdftotext` y `tesseract` para otros tipos de adjuntos.

Ejemplo de mantenimiento de ayuda:

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

Cuando está habilitado, Apple Flow ejecuta una comprobación de mantenimiento ligera con un temporizador, recicla suavemente los ayudantes obsoletos cuando el demonio está inactivo y expone la telemetría de vigilancia de progreso a través de `health` y la API de administración. También puedes activar la misma ruta manualmente con `system: recycle helpers` o `system: maintenance`.

Consulta la configuración completa en [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## Backends de IA

| Conector | Clave |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (nativo) | `apple_flow_connector=ollama` |

Notas:

- `codex-cli`, `claude-cli` y `gemini-cli` ejecutan comandos sin estado.
- `cline` es un agente y admite múltiples proveedores.
- `kilo-cli` es compatible como conector, pero el asistente de configuración `generate-env` actualmente valida `claude-cli`, `codex-cli`, `gemini-cli`, `cline` y `ollama`. Para `kilo-cli`, configura los campos del conector mediante la escritura manual después de la generación.
- `ollama` usa un conector HTTP nativo (`/api/chat`) con el modelo predeterminado `qwen3.5:4b`.

## Arranque recomendado

Mantén la configuración inicial estrecha para que la encuesta sea fácil de verificar:

1. Comienza solo con iMessage y confirma que `apple-flow service status --json` informa sobre el demonio, el acceso a la base de datos de mensajes y la encuesta activa.
2. Habilita una pasarela de Apple a la vez después de que la encuesta sea estable.
3. Activa Companion, la memoria, los seguimientos y el escaneo ambiental al final.

## Aplicación opcional de macOS

Se incluye una aplicación local de incorporación/panel de control de Swift:

- Paquete de aplicación: `dashboard-app/AppleFlowApp.app`
- Zip distribuible: `dashboard-app/AppleFlowApp-macOS.zip`

O compila/exporta desde la documentación fuente: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Valores predeterminados de seguridad

- Aplicación de lista de remitentes permitidos
- Restricciones de espacio de trabajo
- Flujo de trabajo de aprobación para tareas de modificación
- Verificación del remitente de aprobación
- Limitación de velocidad
- Acceso de solo lectura a la base de datos de iMessage
- Supresión de duplicados salientes

Detalles: [SECURITY.md](SECURITY.md)

## Registro de auditoría

Apple Flow ahora es compatible con un registro de análisis primero en CSV mientras mantiene SQLite como el almacén de auditoría canónico.

- Fuente de auditoría canónica: tabla `events` de SQLite (`/audit/events` endpoint).
- Duplicado de análisis: `agent-office/90_logs/events.csv` (solo añadir, una fila por evento).
- Duplicado de markdown legible por humanos: deshabilitado por defecto.

Configuración relevante de `.env`:

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Gestión de servicios

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Documentación

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

## Contribución

Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

MIT — consulta [LICENSE](LICENSE).