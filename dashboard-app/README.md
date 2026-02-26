# Apple Flow Dashboard

`dashboard-app` ships a bundled macOS dashboard app for Apple Flow.

## Contents

- `AppleFlowApp.app` — runnable macOS app bundle
- `AppleFlowApp-macOS.zip` — zipped distribution of the app bundle

## Install and run

1. Open the folder in Finder.
2. If downloaded from the internet, optionally remove quarantine:
   - Open Terminal
   - Run: `xattr -d com.apple.quarantine "AppleFlowApp.app"`
3. Double-click `AppleFlowApp.app` to launch.
4. If prompted, allow permissions required for Apple integrations (Messages, Mail, etc.).

### Install from zip

If you prefer the zip package:

1. Double-click `AppleFlowApp-macOS.zip` to extract.
2. Move `AppleFlowApp.app` to your Applications folder.
3. Launch from Applications or Finder.

## First-time setup

- Make sure the Apple Flow daemon is running with your normal `.env` configuration.
- Ensure the app connects to the local admin API endpoint (default `http://127.0.0.1:8787`).
- Inbound apps (Messages/Mail/Notes/Reminders/Calendar) work only with the configured macOS permissions and polling settings.

## Common setup notes

- Grant Full Disk Access to the terminal/app host process when required for local db access.
- For message routing to work, keep `apple_flow_allowed_senders` and other safety settings configured.
- Mutating commands still follow the normal approval workflow (`task:` / `project:`).

## Troubleshooting

- App launches but shows no data: verify the daemon is running and the API URL is reachable.
- Permission error: check macOS privacy prompts for the app and related Apple apps.
- Connector not responding: confirm `.env` points to the expected connector and credentials are valid.

## Uninstall

Delete `AppleFlowApp.app` (and extracted folders if you used the zip).
