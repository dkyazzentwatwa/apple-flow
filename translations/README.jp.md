<div align="center">

# Apple Flow

**あなたのAppleネイティブAIアシスタント**

macOSのiMessage、メール、リマインダー、メモ、カレンダーからAIを制御します。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flowは、AppleアプリをAI CLI（Codex、Claude、Gemini、Cline、Kilo）に接続するローカルファーストのmacOSデーモンです。デフォルトで送信者許可リスト、変更作業の承認ゲート、ワークスペース制限を強制します。

## スクリーンショット

| ダッシュボード | タスク管理 |
|---|---|
| ![Apple Flow ダッシュボード](../docs/screenshots/dashboard.png) | ![Apple Flow タスク管理](../docs/screenshots/task-management.png) |

| AIポリシーログ | カレンダーイベント |
|---|---|
| ![Apple Flow AIポリシーログ](../docs/screenshots/ai-policy-log.png) | ![Apple Flow カレンダーイベント](../docs/screenshots/calendar-event.png) |

| オフィスブレインストーム |
|---|
| ![Apple Flow オフィスブレインストーム](../docs/screenshots/office-brainstorm.png) |

### ダッシュボードアプリ

| オンボーディング 1 | オンボーディング 2 |
|---|---|
| ![Apple Flow オンボーディング ステップ 1](../docs/screenshots/onboarding-apple-flow1.png) | ![Apple Flow オンボーディング ステップ 2](../docs/screenshots/onboarding-apple-flow2.png) |

| オンボーディング 3 | オンボーディング 4 |
|---|---|
| ![Apple Flow オンボーディング ステップ 3](../docs/screenshots/onboarding-apple-flow3.png) | ![Apple Flow オンボーディング ステップ 4](../docs/screenshots/onboarding-apple-flow4.png) |

| セットアップ構成 | オンボーディングエラー |
|---|---|
| ![Apple Flow アプリセットアップ構成](../docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Apple Flow オンボーディングエラー画面](../docs/screenshots/apple-flow-onboarding-error..png) |

## ハイライト (早読み)

- 強力な安全デフォルト（許可リスト + 承認ゲート + ワークスペース境界）を備えた、ローカルファーストのAppleネイティブAI自動化。
- iMessage、メール、リマインダー、メモ、カレンダーにわたるマルチゲートウェイ操作と、決定的なツールフロー。
- Markdownからの高品質なドキュメント生成、テーマ、目次、引用、エクスポート、セクション更新をサポートする新しいApple Pagesサポート。
- ワークブック作成、シート管理、行挿入セマンティクス、スタイリング自動化をサポートする新しいApple Numbersサポート。
- 専用の`apple-flow-pages`、`apple-flow-numbers`、`apple-flow-mail`、`apple-flow-gateways`スキルを含む、Codex/Claudeスタイルのワークフロー向けグローバルスキルス。
- サービス制御、健全性/ステータスツール、包括的なテストカバレッジを備えた運用に適した操作。

## ここから始める

セットアップパスを1つ選択してください：

| パス | 最適なユーザー | 時間 | エントリポイント |
|---|---|---:|---|
| **AIガイド付きセットアップ (推奨)** | ほとんどのユーザー、最も安全なオンボーディング | 約10分 | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **ワンコマンドスクリプト** | 高速ローカルインストール/自動起動 | 約5-10分 | `./scripts/setup_autostart.sh` |
| **手動セットアップ** | 上級者/カスタム環境 | 15分以上 | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## クイックスタート (AIガイド付き)

### 1) 前提条件

- iMessageにサインインしたmacOS
- 10分
- Homebrew + Python 3.11 + Node

```bash
# Homebrewをインストール (必要に応じて)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python + Nodeをインストール
brew install python@3.11 node
```

### 2) 1つのAI CLIコネクタをインストール

いずれかを選択してください：

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

- Kilo CLI (オプションの高度なコネクタ)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) クローン + ブートストラップ

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) マスタープロンプトで構成を確定

AI CLIを開き、以下を貼り付けます：

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

このフローは以下を処理します：

- ヘルスチェック (`wizard doctor --json`)
- `.env.example`からの完全な`.env`生成
- 書き込み/再起動前の明示的な確認ゲート
- ゲートウェイリソース設定 (リマインダー/メモ/カレンダー)
- 検証 + サービスステータスの確認

### 5) フルディスクアクセスを許可する

1. `システム設定 -> プライバシーとセキュリティ -> フルディスクアクセス` を開きます
2. Apple Flowが使用するPythonバイナリを追加します (セットアップ出力にパスが表示されます)
3. トグルを有効にします

### 6) スモークテスト

iMessageで自分自身にテキストメッセージを送信します：

```text
what files are in my home directory?
```

数秒以内に返信が届くはずです。

## セットアップパス (詳細)

### A) ワンコマンドスクリプトのみ

AIガイド付きセットアップが不要な場合：

```bash
./scripts/setup_autostart.sh
```

`.env`が見つからない場合、`python -m apple_flow setup`を起動して生成します。

### B) 手動セットアップ

`.env`を直接編集します：

```bash
nano .env
```

最小限のキー：

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

リマインダー駆動型ワークフローの場合、`apple_flow_reminders_list_name`と`apple_flow_reminders_archive_list_name`は、`agent-task`や`agent-archive`のようなプレーンなトップレベルリスト名である必要があります。セクション化されたリスト、グループ化されたリスト、ネストされたパス、アクセシビリティ駆動型のフォールバックはサポートされていません。

次に、検証して再起動します：

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## コアコマンド

| コマンド | 動作 |
|---|---|
| `<anything>` | 自然なチャット |
| `idea: <prompt>` | ブレインストーミング |
| `plan: <goal>` | 計画のみ (変更なし) |
| `task: <instruction>` | 変更タスク (承認が必要) |
| `project: <spec>` | マルチステップタスク (承認が必要) |
| `approve <id>` / `deny <id>` / `deny all` | 承認制御 |
| `status` / `status <run_or_request_id>` | 実行/リクエストステータス |
| `health` | デーモンヘルス |
| `history: [query]` | メッセージ履歴 |
| `usage` | 使用状況統計 |
| `help` | ヘルプ + 実用的なヒント |
| `system: mute` / `system: unmute` | コンパニオン制御 |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | ランタイム制御 |
| `system: cancel run <run_id>` | 1つの実行をキャンセル |
| `system: killswitch` | すべてのアクティブなプロバイダープロセスを強制終了 |

### マルチワークスペースルーティング

`@alias`でプレフィックスを付けます：

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### エイリアス付きファイル参照

`.env`で`apple_flow_file_aliases`を介してファイルエイリアスを定義し、プロンプトで`@f:<alias>`で参照します。

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## オプションの統合

すべてのオプションゲートウェイはデフォルトでオフです。

トリガー動作：

- デフォルトのトリガータグは`!!agent`
- メール/リマインダー/メモ/カレンダーの場合、このタグを含むアイテムのみが処理されます
- プロンプト実行前にタグは削除されます
- `apple_flow_trigger_tag`を介して設定

有効化の例：

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

音声メッセージの例：

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

次に、以下でトリガーします：

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:`は送信した正確なテキストを話します。`voice-task:`は最初にタスクを実行し、テキスト結果と合成音声コピーの両方を構成された所有者番号にiMessageで送信します。

コンパニオン + メモリの例：

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Canonical memory v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

添付ファイル処理の例：

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

有効にすると、Apple FlowはiMessage添付ファイル（テキスト/コードファイル、PDF、利用可能な場合はOCRによる画像、`.docx/.pptx/.xlsx`などのOfficeファイル、ローカルWhisper CLIによる音声メモの書き起こし）からプロンプトコンテキストを抽出し、そのコンテキストをチャット、計画、承認実行フローに含めます。

受信したiMessageが音声メモのみの場合、Apple Flowはそれを書き起こし、合成された`voice-task:`リクエストに変換し、テキストと音声合成によるフォローアップの両方で返信します。他の添付ファイルタイプで`pdftotext`や`tesseract`が使用されるのと同様に、STTにはローカルの`whisper` CLIをインストールします。

ヘルパーメンテナンスの例：

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

有効にすると、Apple Flowはタイマーで軽量なメンテナンスチェックを実行し、デーモンがアイドル状態のときに古いヘルパーをソフトリサイクルし、`health`およびadmin APIを介して進捗監視テレメトリを公開します。`system: recycle helpers`または`system: maintenance`を使用して手動で同じパスをトリガーすることもできます。

完全な設定は[docs/ENV_SETUP.md](docs/ENV_SETUP.md)を参照してください。

## AIバックエンド

| コネクタ | キー |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (ネイティブ) | `apple_flow_connector=ollama` |

注記：

- `codex-cli`、`claude-cli`、`gemini-cli`はステートレスコマンドを実行します。
- `cline`はエージェントであり、複数のプロバイダーをサポートします。
- `kilo-cli`はコネクタとしてサポートされていますが、セットアップウィザード`generate-env`は現在`claude-cli`、`codex-cli`、`gemini-cli`、`cline`、`ollama`を検証します。`kilo-cli`の場合、生成後に手動で設定を書き込んでコネクタフィールドを設定してください。
- `ollama`はネイティブHTTPコネクタ (`/api/chat`) をデフォルトモデル`qwen3.5:4b`で使用します。

## 推奨される立ち上げ

ポーリングが簡単に検証できるように、初期セットアップを狭く保ちます：

1. まずiMessageのみから始め、`apple-flow service status --json`がデーモン、メッセージDBアクセス、アクティブなポーリングを報告していることを確認します。
2. ポーリングが安定したら、一度に1つのAppleゲートウェイを有効にします。
3. コンパニオン、メモリ、フォローアップ、アンビエントスキャンは最後に有効にします。

## オプションのmacOSアプリ

ローカルのSwiftオンボーディング/ダッシュボードアプリがバンドルされています：

- アプリバンドル：`dashboard-app/AppleFlowApp.app`
- 配布可能なzip：`dashboard-app/AppleFlowApp-macOS.zip`

または、ソースドキュメントからビルド/エクスポートします：[docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## セキュリティのデフォルト

- 送信者許可リストの強制
- ワークスペースの制限
- 変更タスクの承認ワークフロー
- 承認送信者の検証
- レート制限
- 読み取り専用iMessage DBアクセス
- 重複するアウトバウンドの抑制

詳細：[SECURITY.md](SECURITY.md)

## 監査ログ

Apple Flowは、SQLiteを正規の監査ストアとして維持しながら、CSVファーストのアナリティクスログをサポートするようになりました。

- 正規の監査ソース：SQLiteの`events`テーブル (`/audit/events`エンドポイント)。
- アナリティクスミラー：`agent-office/90_logs/events.csv` (追記専用、イベントごとに1行)。
- 人間が読めるMarkdownミラー：デフォルトで無効。

関連する`.env`設定：

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## サービス管理

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## ドキュメント

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

## 貢献

[CONTRIBUTING.md](CONTRIBUTING.md)を参照してください。

## ライセンス

MIT — [LICENSE](LICENSE)を参照してください。
