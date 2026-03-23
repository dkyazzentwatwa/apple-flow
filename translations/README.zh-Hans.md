<div align="center">

# Apple Flow

**您的Apple原生AI助手**

在macOS上通过iMessage、邮件、提醒事项、备忘录和日历控制AI。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow是一个本地优先的macOS守护程序，它将Apple应用程序连接到AI CLI（Codex、Claude、Gemini、Cline和Kilo）。它默认强制执行发件人白名单、修改工作的批准门槛和工作区限制。

## 屏幕截图

| 仪表板 | 任务管理 |
|---|---|
| ![Apple Flow 仪表板](docs/screenshots/dashboard.png) | ![Apple Flow 任务管理](docs/screenshots/task-management.png) |

| AI策略日志 | 日历事件 |
|---|---|
| ![Apple Flow AI策略日志](docs/screenshots/ai-policy-log.png) | ![Apple Flow 日历事件](docs/screenshots/calendar-event.png) |

| 办公室头脑风暴 |
|---|
| ![Apple Flow 办公室头脑风暴](docs/screenshots/office-brainstorm.png) |

### 仪表板应用程序

| 入门 1 | 入门 2 |
|---|---|
| ![Apple Flow 入门步骤 1](docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow 入门步骤 2](docs/screenshots/onboarding-apple-flow2.png) |

| 入门 3 | 入门 4 |
|---|---|
| ![Apple Flow 入门步骤 3](docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow 入门步骤 4](docs/screenshots/onboarding-apple-flow4.png) |

| 设置配置 | 入门错误 |
|---|---|
| ![Apple Flow 应用程序设置配置](docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Apple Flow 入门错误屏幕](docs/screenshots/apple-flow-onboarding-error..png) |

## 亮点 (快速阅读)

- 本地优先的Apple原生AI自动化，具有强大的安全默认设置（白名单+审批门槛+工作区边界）。
- 通过iMessage、邮件、提醒事项、备忘录和日历进行多网关操作，具有确定性工具流。
- 新的Apple Pages支持从Markdown生成高质量文档，包括主题、目录、引用、导出和章节更新。
- 新的Apple Numbers支持工作簿创建、工作表管理、行插入语义和样式自动化。
- 适用于Codex/Claude风格工作流的全球技能包，包括专用的`apple-flow-pages`、`apple-flow-numbers`、`apple-flow-mail`和`apple-flow-gateways`技能。
- 具有服务控制、健康/状态工具和全面测试覆盖率的生产友好型操作。

## 从这里开始

选择一个设置路径：

| 路径 | 最适合 | 时间 | 入口点 |
|---|---|---:|---|
| **AI引导式设置 (推荐)** | 大多数用户，最安全的入门方式 | 约10分钟 | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **一键式脚本** | 快速本地安装/自动启动 | 约5-10分钟 | `./scripts/setup_autostart.sh` |
| **手动设置** | 高级/自定义环境 | 15分钟以上 | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## 快速入门 (AI引导式)

### 1) 先决条件

- 登录iMessage的macOS
- 10分钟
- Homebrew + Python 3.11 + Node

```bash
# 安装Homebrew (如果需要)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装Python + Node
brew install python@3.11 node
```

### 2) 安装一个AI CLI连接器

选择一个：

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

- Kilo CLI (可选的高级连接器)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) 克隆 + 引导

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) 使用主提示完成配置

打开您的AI CLI并粘贴：

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

该流程处理：

- 健康检查 (`wizard doctor --json`)
- 从`.env.example`完整生成`.env`
- 写入/重启前的明确确认门槛
- 网关资源设置（提醒事项/备忘录/日历）
- 验证 + 服务状态验证

### 5) 授予完全磁盘访问权限

1. 打开 `系统设置 -> 隐私与安全性 -> 完全磁盘访问权限`
2. 添加Apple Flow使用的Python二进制文件（设置输出显示路径）
3. 启用开关

### 6) 冒烟测试

在iMessage中给自己发送消息：

```text
what files are in my home directory?
```

您应该会在几秒钟内收到回复。

## 设置路径 (详细)

### A) 仅一键式脚本

如果您不需要AI引导式设置：

```bash
./scripts/setup_autostart.sh
```

如果`.env`缺失，它会启动`python -m apple_flow setup`来生成一个。

### B) 手动设置

直接编辑`.env`：

```bash
nano .env
```

最小键：

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

对于基于提醒事项的工作流，`apple_flow_reminders_list_name`和`apple_flow_reminders_archive_list_name`必须是简单的顶级列表名称，例如`agent-task`和`agent-archive`。不支持分段列表、分组列表、嵌套路径和基于辅助功能的备用方案。

然后验证并重启：

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## 核心命令

| 命令 | 作用 |
|---|---|
| `<anything>` | 自然聊天 |
| `idea: <prompt>` | 头脑风暴 |
| `plan: <goal>` | 仅计划 (无更改) |
| `task: <instruction>` | 修改任务 (需要批准) |
| `project: <spec>` | 多步骤任务 (需要批准) |
| `approve <id>` / `deny <id>` / `deny all` | 批准控制 |
| `status` / `status <run_or_request_id>` | 运行/请求状态 |
| `health` | 守护程序健康 |
| `history: [query]` | 消息历史 |
| `usage` | 使用统计 |
| `help` | 帮助 + 实用技巧 |
| `system: mute` / `system: unmute` | 伴侣控制 |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | 运行时控制 |
| `system: cancel run <run_id>` | 取消一个运行 |
| `system: killswitch` | 终止所有活动提供者进程 |

### 多工作区路由

前缀为`@alias`：

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### 带有别名的文件引用

通过`apple_flow_file_aliases`在`.env`中定义文件别名，并在提示中通过`@f:<alias>`引用它们。

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## 可选集成

所有可选网关默认关闭。

触发行为：

- 默认触发标签是`!!agent`
- 对于邮件/提醒事项/备忘录/日历，只处理包含该标签的项
- 提示执行前会删除标签
- 通过`apple_flow_trigger_tag`配置

启用示例：

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

语音消息示例：

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

然后触发：

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:`会说出您发送的精确文本。`voice-task:`会首先执行任务，然后将文本结果和合成音频副本通过iMessage发送给配置的所有者号码。

伴侣 + 内存示例：

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# 规范内存 v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

附件处理示例：

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

启用后，Apple Flow会从iMessage附件（文本/代码文件、PDF、通过OCR（如果可用）的图像、`.docx/.pptx/.xlsx`等Office文件以及通过本地Whisper CLI转录的音频语音备忘录）中提取提示上下文，并将该上下文包含在聊天、规划和审批执行流中。

如果收到的iMessage只是一个语音备忘录，Apple Flow现在会将其转录，转换为合成的`voice-task:`请求，并以文本和口语TTS回复。安装本地`whisper` CLI以进行STT，类似于`pdftotext`和`tesseract`用于其他附件类型的方式。

助手维护示例：

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

启用后，Apple Flow会按计时器运行轻量级维护检查，在守护程序空闲时软回收过期的助手，并通过`health`和管理员API公开前向进度监视遥测。您也可以使用`system: recycle helpers`或`system: maintenance`手动触发相同的路径。

完整设置请参阅[docs/ENV_SETUP.md](docs/ENV_SETUP.md)。

## AI后端

| 连接器 | 键 |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (原生) | `apple_flow_connector=ollama` |

注意：

- `codex-cli`、`claude-cli`和`gemini-cli`运行无状态命令。
- `cline`是代理型，支持多个提供商。
- `kilo-cli`作为连接器受到支持，但设置向导`generate-env`目前验证`claude-cli`、`codex-cli`、`gemini-cli`、`cline`和`ollama`。对于`kilo-cli`，在生成后通过手动配置写入设置连接器字段。
- `ollama`使用原生HTTP连接器 (`/api/chat`)，默认模型为`qwen3.5:4b`。

## 推荐启动

保持初始设置狭窄，以便于验证轮询：

1. 从仅iMessage开始，并确认`apple-flow service status --json`报告守护程序、消息DB访问和活动轮询。
2. 在轮询稳定后，一次启用一个Apple网关。
3. 最后打开伴侣、内存、后续和环境扫描。

## 可选macOS应用程序

捆绑了一个本地Swift入门/仪表板应用程序：

- 应用程序包：`dashboard-app/AppleFlowApp.app`
- 可分发zip：`dashboard-app/AppleFlowApp-macOS.zip`

或从源文档构建/导出：[docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## 安全默认值

- 发件人白名单强制执行
- 工作区限制
- 修改任务的审批工作流
- 审批请求者验证
- 速率限制
- iMessage数据库只读访问
- 重复出站抑制

详情：[SECURITY.md](SECURITY.md)

## 审计日志

Apple Flow现在支持CSV优先的分析日志，同时将SQLite保留为规范的审计存储。

- 规范审计源：SQLite `events`表（`/audit/events`端点）。
- 分析镜像：`agent-office/90_logs/events.csv`（仅追加，每事件一行）。
- 人类可读的markdown镜像：默认禁用。

相关的`.env`设置：

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## 服务管理

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## 文档

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

## 贡献

请参阅[CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

MIT — 请参阅[LICENSE](LICENSE)。