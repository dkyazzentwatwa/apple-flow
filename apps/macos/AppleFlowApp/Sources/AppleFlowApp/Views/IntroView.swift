import SwiftUI

struct IntroView: View {
    @ObservedObject var viewModel: AppViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Welcome to AppleFlowApp")
                        .font(.largeTitle.weight(.bold))
                    Text("This app helps you safely configure Apple Flow and then operate it from a local control panel.")
                        .foregroundStyle(AppTheme.subtleText)
                }

                SectionCard("What This App Does") {
                    VStack(alignment: .leading, spacing: 8) {
                        introLine("Runs environment checks for Python, iMessage DB access, connector, and token readiness.")
                        introLine("Guides setup and generates a full `.env` preview before applying changes.")
                        introLine("Installs/starts launchd services and verifies health.")
                        introLine("Provides runtime operations: approvals, sessions, events, logs, and config edits.")
                    }
                }

                SectionCard("Recommended Flow") {
                    VStack(alignment: .leading, spacing: 8) {
                        introLine("1. Complete onboarding fields and generate preview.")
                        introLine("2. Apply setup to write config, validate, and start services.")
                        introLine("3. Use Control Panel tabs to monitor and operate Apple Flow.")
                    }
                }

                SectionCard("Safety & Notes") {
                    VStack(alignment: .leading, spacing: 8) {
                        introLine("Mutating operations stay behind validation and service checks.")
                        introLine("Config edits are saved to your local `.env` in this repo.")
                        introLine("Agent Office can be scaffolded automatically during setup when enabled.")
                    }
                }

                HStack(spacing: 12) {
                    Button("Continue to Setup") {
                        viewModel.finishIntroAndContinue()
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Skip to Control Panel") {
                        Task { await viewModel.skipIntroToControlPanel() }
                    }
                    .buttonStyle(.bordered)

                    Spacer()
                }
            }
            .padding(AppTheme.pagePadding)
        }
    }

    private func introLine(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(AppTheme.success)
                .padding(.top, 2)
            Text(text)
                .font(.callout)
        }
    }
}
