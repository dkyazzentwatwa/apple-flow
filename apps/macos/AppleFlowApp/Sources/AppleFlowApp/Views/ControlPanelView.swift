import SwiftUI
import Foundation

struct ControlPanelView: View {
    @ObservedObject var viewModel: AppViewModel
    private static let refreshDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .medium
        return formatter
    }()

    var body: some View {
        TabView {
            overviewTab
                .tabItem { Label("Overview", systemImage: "speedometer") }

            approvalsTab
                .tabItem { Label("Approvals", systemImage: "checkmark.seal") }

            sessionsTab
                .tabItem { Label("Sessions", systemImage: "person.3") }

            eventsTab
                .tabItem { Label("Events", systemImage: "clock.arrow.circlepath") }

            logsTab
                .tabItem { Label("Logs", systemImage: "doc.text.magnifyingglass") }

            configTab
                .tabItem { Label("Config", systemImage: "slider.horizontal.3") }
        }
        .padding(12)
        .toolbar {
            ToolbarItemGroup(placement: .automatic) {
                Button("Return to Config") {
                    viewModel.returnToConfig()
                }
                .buttonStyle(.bordered)

                Button(viewModel.isRefreshingControlPanel ? "Refreshing..." : "Refresh") {
                    Task { await viewModel.refreshControlPanel() }
                }
                .disabled(viewModel.isRefreshingControlPanel)
                .buttonStyle(.borderedProminent)
            }
        }
    }

    private var overviewTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Apple Flow Control Panel")
                        .font(.largeTitle.weight(.bold))
                    Text("Monitor runtime health, approvals, sessions, logs, and live configuration.")
                        .foregroundStyle(AppTheme.subtleText)
                    StatusChip(text: viewModel.statusMessage, tone: viewModel.statusTone)

                    HStack(spacing: 8) {
                        StatusChip(text: "Last refresh: \(lastRefreshText)", tone: .info)
                        if !viewModel.refreshWarnings.isEmpty {
                            StatusChip(
                                text: "Warnings: \(viewModel.refreshWarnings.count)",
                                tone: .warning
                            )
                        }
                    }
                }

                if !viewModel.refreshWarnings.isEmpty {
                    SectionCard("Refresh Warnings", subtitle: "Some panels may be stale") {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(viewModel.refreshWarnings, id: \.self) { warning in
                                Text("• \(warning)")
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.warning)
                            }
                        }
                    }
                }

                if let status = viewModel.serviceStatus {
                    SectionCard("Service Status") {
                        VStack(alignment: .leading, spacing: 8) {
                            statusLine("launchd loaded", value: status.launchdLoaded ? "yes" : "no")
                            statusLine("launchd pid", value: status.launchdPid.map(String.init) ?? "-")
                            statusLine("daemon process detected", value: status.daemonProcessDetected ? "yes" : "no")
                            statusLine("admin API healthy", value: status.healthy ? "yes" : "no")
                            statusLine("plist", value: status.plistPath)

                            HStack {
                                Button("Install") { Task { await viewModel.installService() } }
                                Button("Start") { Task { await viewModel.startService() } }
                                Button("Stop") { Task { await viewModel.stopService() } }
                                Button("Restart") { Task { await viewModel.restartService() } }
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }

                if let metrics = viewModel.metrics {
                    SectionCard("Runtime Metrics") {
                        VStack(alignment: .leading, spacing: 8) {
                            statusLine("active sessions", value: "\(metrics.activeSessions)")
                            statusLine("pending approvals", value: "\(metrics.pendingApprovals)")
                            statusLine("recent events", value: "\(metrics.recentEvents)")
                        }
                    }
                }
            }
            .padding(.vertical, 8)
        }
    }

    private var approvalsTab: some View {
        VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
            Text("Pending Approvals")
                .font(.title2.weight(.bold))

            if viewModel.approvals.isEmpty {
                SectionCard("No pending approvals") {
                    Text("Mutating requests waiting for approval will appear here.")
                        .foregroundStyle(AppTheme.subtleText)
                }
            } else {
                List(viewModel.approvals) { approval in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(approval.summary)
                            .font(.headline)
                        Text("request_id: \(approval.requestId)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("Approve") {
                                Task { await viewModel.approve(approval.requestId) }
                            }
                            .buttonStyle(.borderedProminent)

                            Button("Deny") {
                                Task { await viewModel.deny(approval.requestId) }
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    private var sessionsTab: some View {
        VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
            Text("Sessions")
                .font(.title2.weight(.bold))

            List(viewModel.sessions) { session in
                VStack(alignment: .leading, spacing: 4) {
                    Text(session.sender)
                        .font(.headline)
                    if let threadID = session.threadId {
                        Text("thread: \(threadID)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let lastSeen = session.lastSeenAt {
                        Text("last seen: \(lastSeen)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var eventsTab: some View {
        VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
            Text("Audit Events")
                .font(.title2.weight(.bold))

            List(viewModel.events) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.eventType)
                        .font(.headline)
                    if let createdAt = event.createdAt {
                        Text(createdAt)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let payload = event.payloadJson, !payload.isEmpty {
                        Text(payload)
                            .font(.caption)
                            .lineLimit(3)
                    }
                }
            }
        }
    }

    private var logsTab: some View {
        VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
            Text("Logs")
                .font(.title2.weight(.bold))

            HStack {
                Picker("Stream", selection: $viewModel.logStream) {
                    Text("stderr").tag("stderr")
                    Text("stdout").tag("stdout")
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 220)

                Stepper("Lines: \(viewModel.logLines)", value: $viewModel.logLines, in: 50...5000, step: 50)
                    .frame(maxWidth: 220)

                Button("Refresh Logs") {
                    Task { await viewModel.refreshLogs() }
                }
                .buttonStyle(.bordered)
            }

            TextEditor(text: $viewModel.logsText)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: 420)
        }
    }

    private var configTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
                SectionCard("Config Editor", subtitle: "Guided `.env` editing with validation-aware hints") {
                    VStack(alignment: .leading, spacing: 8) {
                        statusLine("Editing .env at", value: viewModel.envFilePath)
                        HStack(spacing: 10) {
                            if let success = viewModel.lastValidationSucceeded {
                                StatusChip(text: viewModel.lastValidationMessage, tone: success ? .success : .error)
                            } else {
                                StatusChip(text: viewModel.lastValidationMessage, tone: .info)
                            }
                            StatusChip(text: "Unsaved changes: \(viewModel.unsavedConfigChangeCount)", tone: viewModel.unsavedConfigChangeCount > 0 ? .warning : .success)
                        }
                    }
                }

                SectionCard("Find Fields") {
                    HStack(spacing: 10) {
                        TextField("Search by key or label", text: $viewModel.configSearchQuery)
                            .textFieldStyle(.roundedBorder)
                        Picker("Filter", selection: $viewModel.configFilter) {
                            ForEach(ConfigFilterScope.allCases) { scope in
                                Text(scope.rawValue).tag(scope)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 420)
                    }
                }

                ForEach(viewModel.groupedFilteredConfigDescriptors, id: \.0.id) { category, descriptors in
                    SectionCard(category.rawValue, subtitle: "\(descriptors.count) field\(descriptors.count == 1 ? "" : "s")") {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(descriptors) { descriptor in
                                configFieldRow(descriptor)
                            }
                        }
                    }
                }

                SectionCard("Apply Changes") {
                    HStack {
                        Button("Validate") {
                            Task { await viewModel.validateConfigOnly() }
                        }
                        .buttonStyle(.bordered)

                        Button("Apply + Validate + Restart") {
                            Task { await viewModel.applyConfigValidateAndRestart() }
                        }
                        .buttonStyle(.borderedProminent)

                        Button("Revert All") {
                            viewModel.revertAllConfigChanges()
                        }
                        .buttonStyle(.bordered)

                        Button("Refresh from .env") {
                            Task { await viewModel.refreshControlPanel() }
                        }
                        .buttonStyle(.bordered)
                    }
                }

                if !viewModel.configValidationErrors.isEmpty || !viewModel.configValidationWarnings.isEmpty {
                    SectionCard("Validation Details") {
                        VStack(alignment: .leading, spacing: 8) {
                            if !viewModel.configValidationErrors.isEmpty {
                                Text("Errors")
                                    .font(.headline)
                                    .foregroundStyle(AppTheme.error)
                                ForEach(viewModel.configValidationErrors, id: \.self) { err in
                                    Text("• \(err)")
                                        .foregroundStyle(AppTheme.error)
                                        .font(.caption)
                                }
                            }

                            if !viewModel.configValidationWarnings.isEmpty {
                                Text("Warnings")
                                    .font(.headline)
                                    .foregroundStyle(AppTheme.warning)
                                    .padding(.top, 6)
                                ForEach(viewModel.configValidationWarnings, id: \.self) { warning in
                                    Text("• \(warning)")
                                        .font(.caption)
                                }
                            }
                        }
                    }
                }
            }
            .padding(.vertical, 8)
        }
    }

    @ViewBuilder
    private func configFieldRow(_ descriptor: ConfigFieldDescriptor) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(descriptor.label)
                    .font(.subheadline.weight(.semibold))
                InlineHelpBadge(descriptor: descriptor)
                if descriptor.required {
                    StatusChip(text: "Required", tone: .warning)
                }
                Spacer()
                Text(descriptor.key)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .center, spacing: 8) {
                fieldInput(descriptor)

                if descriptor.sensitive {
                    Button(viewModel.isSensitiveRevealed(descriptor.key) ? "Hide" : "Reveal") {
                        viewModel.toggleSensitiveReveal(descriptor.key)
                    }
                    .buttonStyle(.bordered)
                }

                FieldValidationBadge(state: viewModel.validationState(for: descriptor.key))

                if viewModel.isFieldChanged(descriptor.key) {
                    Button("Reset") {
                        viewModel.resetConfigValue(for: descriptor.key)
                    }
                    .buttonStyle(.bordered)
                }
            }

            Text(descriptor.validationHint)
                .font(.caption2)
                .foregroundStyle(AppTheme.subtleText)
        }
        .padding(10)
        .background(Color.white.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    @ViewBuilder
    private func fieldInput(_ descriptor: ConfigFieldDescriptor) -> some View {
        let binding = Binding(
            get: { viewModel.configValues[descriptor.key, default: ""] },
            set: { viewModel.configValues[descriptor.key] = $0 }
        )

        if descriptor.sensitive && !viewModel.isSensitiveRevealed(descriptor.key) {
            SecureField(descriptor.placeholder, text: binding)
                .textFieldStyle(.roundedBorder)
        } else {
            TextField(descriptor.placeholder, text: binding)
                .textFieldStyle(.roundedBorder)
        }
    }

    private func statusLine(_ title: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .foregroundStyle(AppTheme.subtleText)
            Spacer()
            Text(value)
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
        }
    }

    private var lastRefreshText: String {
        guard let lastRefreshAt = viewModel.lastRefreshAt else {
            return "Never"
        }
        return Self.refreshDateFormatter.string(from: lastRefreshAt)
    }
}
