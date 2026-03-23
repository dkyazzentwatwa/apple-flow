<div align="center">

# Apple Flow

**Votre Assistant IA natif d'Apple**

Contrôlez l'IA depuis iMessage, Mail, Rappels, Notes et Calendrier sur macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow est un démon macOS local qui relie les applications Apple aux CLI IA (Codex, Claude, Gemini, Cline et Kilo). Il applique des listes d'expéditeurs autorisés, des portes d'approbation pour les travaux de modification et des restrictions d'espace de travail par défaut.

## Captures d'écran

| Tableau de bord | Gestion des tâches |
|---|---|
| ![Tableau de bord Apple Flow](docs/screenshots/dashboard.png) | ![Gestion des tâches Apple Flow](docs/screenshots/task-management.png) |

| Journal des politiques IA | Événement du calendrier |
|---|---|
| ![Journal des politiques IA Apple Flow](docs/screenshots/ai-policy-log.png) | ![Événement du calendrier Apple Flow](docs/screenshots/calendar-event.png) |

| Brainstorming de bureau |
|---|
| ![Brainstorming de bureau Apple Flow](docs/screenshots/office-brainstorm.png) |

### Application Tableau de bord

| Intégration 1 | Intégration 2 |
|---|---|
| ![Étape 1 d'intégration d'Apple Flow](docs/screenshots/onboarding-apple-flow1.png) | ![Étape 2 d'intégration d'Apple Flow](docs/screenshots/onboarding-apple-flow2.png) |

| Intégration 3 | Intégration 4 |
|---|---|
| ![Étape 3 d'intégration d'Apple Flow](docs/screenshots/onboarding-apple-flow3.png) | ![Étape 4 d'intégration d'Apple Flow](docs/screenshots/onboarding-apple-flow4.png) |

| Configuration de l'installation | Erreur d'intégration |
|---|---|
| ![Configuration de l'installation de l'application Apple Flow](docs/screenshots/AppleFlowApp-setup-configuration-screen..png) | ![Écran d'erreur d'intégration d'Apple Flow](docs/screenshots/apple-flow-onboarding-error..png) |

## Faits saillants (lecture rapide)

- Automatisation IA native d'Apple, locale d'abord, avec de solides valeurs par défaut de sécurité (liste blanche + portes d'approbation + limites d'espace de travail).
- Opérations multi-passerelles via iMessage, Mail, Rappels, Notes et Calendrier avec des flux d'outils déterministes.
- Nouveau support Apple Pages pour la génération de documents de haute qualité à partir de Markdown, incluant des thèmes, des tables des matières, des citations, des exportations et des mises à jour de sections.
- Nouveau support Apple Numbers pour la création de classeurs, la gestion de feuilles, la sémantique d'insertion de lignes et l'automatisation du style.
- Packs de compétences globaux pour les flux de travail de style Codex/Claude, y compris les compétences dédiées `apple-flow-pages`, `apple-flow-numbers`, `apple-flow-mail` et `apple-flow-gateways`.
- Opérations prêtes pour la production avec des contrôles de service, des outils de santé/état et une couverture de test complète.

## Commencez ici

Choisissez un chemin de configuration :

| Chemin | Idéal pour | Temps | Point d'entrée |
|---|---|---:|---|
| **Configuration guidée par l'IA (recommandé)** | La plupart des utilisateurs, intégration la plus sûre | ~10 min | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **Script à une commande** | Installation locale/démarrage automatique rapide | ~5-10 min | `./scripts/setup_autostart.sh` |
| **Configuration manuelle** | Environnements avancés/personnalisés | ~15+ min | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Démarrage rapide (guidé par l'IA)

### 1) Prérequis

- macOS avec iMessage connecté
- 10 minutes
- Homebrew + Python 3.11 + Node

```bash
# Installer Homebrew (si nécessaire)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Installer Python + Node
brew install python@3.11 node
```

### 2) Installer un connecteur CLI IA

Choisissez-en un :

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

- Kilo CLI (connecteur avancé optionnel)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Cloner + Amorcer

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Finaliser la configuration avec le prompt maître de l'IA

Ouvrez votre CLI IA et collez :

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

Ce flux gère :

- Les vérifications de santé (`wizard doctor --json`)
- La génération complète de `.env` à partir de `.env.example`
- Les portes de confirmation explicites avant les écritures/redémarrages
- La configuration des ressources de passerelle (Rappels/Notes/Calendrier)
- La validation + la vérification de l'état du service

### 5) Accorder un accès complet au disque

1. Ouvrez `Réglages Système -> Confidentialité et sécurité -> Accès complet au disque`
2. Ajoutez le binaire Python utilisé par Apple Flow (la sortie de l'installation indique le chemin)
3. Activez le bouton

### 6) Test de fumée

Envoyez-vous un message dans iMessage :

```text
what files are in my home directory?
```

Vous devriez recevoir une réponse en quelques secondes.

## Chemins de configuration (détaillés)

### A) Script à une commande uniquement

Si vous ne voulez pas de configuration guidée par l'IA :

```bash
./scripts/setup_autostart.sh
```

Si `.env` est manquant, il lance `python -m apple_flow setup` pour en générer un.

### B) Configuration manuelle

Modifiez `.env` directement :

```bash
nano .env
```

Clés minimales :

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Pour les flux de travail basés sur les Rappels, `apple_flow_reminders_list_name` et `apple_flow_reminders_archive_list_name` doivent être des noms de listes de premier niveau simples tels que `agent-task` et `agent-archive`. Les listes sectionnées, les listes groupées, les chemins imbriqués et les solutions de repli basées sur l'accessibilité ne sont pas pris en charge.

Ensuite, validez et redémarrez :

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Commandes principales

| Commande | Ce qu'elle fait |
|---|---|
| `<anything>` | Chat naturel |
| `idea: <prompt>` | Brainstorming |
| `plan: <goal>` | Plan uniquement (aucun changement) |
| `task: <instruction>` | Tâche de modification (approbation requise) |
| `project: <spec>` | Tâche en plusieurs étapes (approbation requise) |
| `approve <id>` / `deny <id>` / `deny all` | Contrôles d'approbation |
| `status` / `status <run_or_request_id>` | Statut d'exécution/demande |
| `health` | Santé du démon |
| `history: [query]` | Historique des messages |
| `usage` | Statistiques d'utilisation |
| `help` | Aide + conseils pratiques |
| `system: mute` / `system: unmute` | Contrôles compagnon |
| `system: stop` / `system: restart` / `system: recycle helpers` / `system: maintenance` / `system: kill provider` | Contrôles d'exécution |
| `system: cancel run <run_id>` | Annuler une exécution |
| `system: killswitch` | Arrêter tous les processus de fournisseur actifs |

### Routage multi-espace de travail

Préfixez avec `@alias` :

```text
task: @healer run the test suite
task: @web-app deploy to staging
@api show recent errors
```

### Références de fichiers avec des alias

Définissez des alias de fichiers dans `.env` via `apple_flow_file_aliases` et référencez-les dans les invites avec `@f:<alias>`.

```text
plan: summarize @f:context-bank
task: review @f:runbook and propose updates
```

## Intégrations optionnelles

Toutes les passerelles optionnelles sont désactivées par défaut.

Comportement du déclencheur :

- L'étiquette de déclenchement par défaut est `!!agent`
- Pour Mail/Rappels/Notes/Calendrier, seuls les éléments contenant cette étiquette sont traités
- L'étiquette est supprimée avant l'exécution du prompt
- Configurez via `apple_flow_trigger_tag`

Exemples d'activation :

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Exemples de messages vocaux :

```env
apple_flow_phone_owner_number=+15551234567
apple_flow_phone_tts_voice=
apple_flow_phone_tts_rate=180
apple_flow_phone_tts_engine=auto
apple_flow_phone_piper_model_path=/Users/you/models/en_US-amy-medium.onnx
```

Ensuite, déclenchez avec :

```text
voice: standup starts in 10 minutes
voice-task: analyze my workspace
```

`voice:` prononce le texte exact que vous envoyez. `voice-task:` exécute la tâche en premier, puis envoie le résultat texte et une copie audio synthétisée via iMessage au numéro du propriétaire configuré.

Exemples de compagnon + mémoire :

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Mémoire canonique v2
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_migrate_on_start=true
```

Exemple de traitement des pièces jointes :

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

Lorsqu'elle est activée, Apple Flow extrait le contexte de l'invite des pièces jointes iMessage (fichiers texte/code, PDF, images via OCR si disponible, fichiers Office tels que `.docx/.pptx/.xlsx` et notes vocales audio via la transcription CLI Whisper locale) et inclut ce contexte dans les flux de chat, de planification et d'exécution d'approbation.

Si un iMessage entrant est simplement une note vocale, Apple Flow la transcrit, la transforme en une requête `voice-task:` synthétique et répond avec le texte et un suivi TTS parlé. Installez une CLI locale `whisper` pour le STT, de la même manière que `pdftotext` et `tesseract` sont utilisés pour d'autres types de pièces jointes.

Exemple de maintenance de l'assistant :

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

Lorsqu'elle est activée, Apple Flow exécute une vérification de maintenance légère à intervalles réguliers, recycle en douceur les assistants obsolètes lorsque le démon est inactif et expose la télémétrie de surveillance de la progression via `health` et l'API d'administration. Vous pouvez également déclencher le même chemin manuellement avec `system: recycle helpers` ou `system: maintenance`.

Voir les paramètres complets dans [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## Backends IA

| Connecteur | Clé |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |
| Ollama (natif) | `apple_flow_connector=ollama` |

Notes :

- `codex-cli`, `claude-cli` et `gemini-cli` exécutent des commandes sans état.
- `cline` est agentique et prend en charge plusieurs fournisseurs.
- `kilo-cli` est pris en charge en tant que connecteur, mais l'assistant de configuration `generate-env` valide actuellement `claude-cli`, `codex-cli`, `gemini-cli`, `cline` et `ollama`. Pour `kilo-cli`, configurez les champs du connecteur via une écriture de configuration manuelle après la génération.
- `ollama` utilise un connecteur HTTP natif (`/api/chat`) avec le modèle par défaut `qwen3.5:4b`.

## Démarrage recommandé

Maintenez une configuration initiale étroite pour faciliter la vérification du sondage :

1. Commencez uniquement avec iMessage et confirmez que `apple-flow service status --json` indique le démon, l'accès à la base de données Messages et un sondage actif.
2. Activez une passerelle Apple à la fois après que le sondage soit stable.
3. Activez le compagnon, la mémoire, les suivis et le scan ambiant en dernier.

## Application macOS optionnelle

Une application locale Swift d'intégration/tableau de bord est incluse :

- Bundle d'application : `dashboard-app/AppleFlowApp.app`
- Zip distribuable : `dashboard-app/AppleFlowApp-macOS.zip`

Ou construisez/exportez à partir des documents sources : [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Défauts de sécurité

- Application de la liste blanche des expéditeurs
- Restrictions d'espace de travail
- Flux de travail d'approbation pour les tâches de modification
- Vérification de l'expéditeur de l'approbation
- Limitation de débit
- Accès en lecture seule à la base de données iMessage
- Suppression des doublons sortants

Détails : [SECURITY.md](SECURITY.md)

## Journalisation d'audit

Apple Flow prend désormais en charge un journal d'analyse d'abord en CSV tout en conservant SQLite comme magasin d'audit canonique.

- Source d'audit canonique : table `events` de SQLite (point d'extrémité `/audit/events`).
- Miroir d'analyse : `agent-office/90_logs/events.csv` (ajout uniquement, une ligne par événement).
- Miroir Markdown lisible par l'homme : désactivé par défaut.

Paramètres `.env` pertinents :

- `apple_flow_enable_csv_audit_log=true`
- `apple_flow_csv_audit_log_path=agent-office/90_logs/events.csv`
- `apple_flow_csv_audit_include_headers_if_missing=true`
- `apple_flow_enable_markdown_automation_log=false`

## Gestion des services

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Documentation

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

## Contribution

Voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — voir [LICENSE](LICENSE).