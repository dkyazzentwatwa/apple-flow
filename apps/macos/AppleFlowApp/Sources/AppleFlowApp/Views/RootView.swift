import SwiftUI

struct RootView: View {
    @ObservedObject var viewModel: AppViewModel

    var body: some View {
        Group {
            switch viewModel.route {
            case .intro:
                IntroView(viewModel: viewModel)

            case .loading:
                VStack(spacing: 14) {
                    ProgressView()
                    Text("Loading Apple Flow...")
                        .font(.headline)
                    StatusChip(text: viewModel.statusMessage, tone: viewModel.statusTone)
                }
                .padding(24)

            case .onboarding:
                OnboardingView(viewModel: viewModel)

            case .controlPanel:
                ControlPanelView(viewModel: viewModel)
            }
        }
        .background(AppTheme.background.ignoresSafeArea())
        .onAppear {
            viewModel.onAppear()
        }
        .overlay(alignment: .bottom) {
            if let error = viewModel.errorMessage, !error.isEmpty {
                SectionCard("Action Required", subtitle: "The last command failed") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(error)
                            .font(.callout)
                            .foregroundStyle(AppTheme.error)
                            .textSelection(.enabled)

                        HStack {
                            Button("Dismiss") {
                                viewModel.clearErrorMessage()
                            }
                            .buttonStyle(.bordered)

                            Button("Copy Details") {
                                viewModel.copyErrorMessage()
                            }
                            .buttonStyle(.bordered)

                            if viewModel.canRetryLastAction {
                                Button("Retry") {
                                    viewModel.retryLastAction()
                                }
                                .buttonStyle(.borderedProminent)
                            }

                            if viewModel.route == .onboarding {
                                Button("Reset Onboarding") {
                                    viewModel.resetOnboardingState()
                                }
                                .buttonStyle(.bordered)
                            }

                            Spacer()
                        }
                    }
                }
                .padding()
                .frame(maxWidth: 920)
            }
        }
    }
}
