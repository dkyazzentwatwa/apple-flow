import SwiftUI
import AppKit

struct OnboardingView: View {
    @ObservedObject var viewModel: AppViewModel
    @State private var showDoctorErrors = true

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.cardSpacing) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Apple Flow Onboarding")
                        .font(.largeTitle.weight(.bold))
                    Text("Configure checks, connector setup, Apple gateways, and service installation.")
                        .foregroundStyle(AppTheme.subtleText)
                    StatusChip(text: viewModel.statusMessage, tone: viewModel.statusTone)
                }

                HStack(spacing: 10) {
                    Button("Collapse All") {
                        viewModel.collapseAllOnboardingSections()
                    }
                    .buttonStyle(.bordered)
                    Button("Expand All") {
                        viewModel.expandAllOnboardingSections()
                    }
                    .buttonStyle(.bordered)
                }

                if let doctor = viewModel.doctor {
                    CollapsibleSectionCard(
                        "System Checks",
                        subtitle: "Environment readiness before setup",
                        isCollapsed: viewModel.isOnboardingSectionCollapsed(OnboardingSection.checks.rawValue),
                        onToggle: { viewModel.toggleOnboardingSectionCollapse(OnboardingSection.checks.rawValue) }
                    ) {
                        doctorCardContent(doctor)
                    }
                }

                CollapsibleSectionCard(
                    "Setup Progress",
                    subtitle: "Follow these milestones to complete onboarding",
                    isCollapsed: viewModel.isOnboardingSectionCollapsed(OnboardingSection.progress.rawValue),
                    onToggle: { viewModel.toggleOnboardingSectionCollapse(OnboardingSection.progress.rawValue) }
                ) {
                    progressStripContent
                }
                CollapsibleSectionCard(
                    "Core Configuration",
                    subtitle: "Identity, workspace, and connector settings",
                    isCollapsed: viewModel.isOnboardingSectionCollapsed(OnboardingSection.core.rawValue),
                    onToggle: { viewModel.toggleOnboardingSectionCollapse(OnboardingSection.core.rawValue) }
                ) {
                    coreConfigurationContent
                }
                CollapsibleSectionCard(
                    "Optional Gateways",
                    subtitle: "Enable Apple app channels and customize resource names",
                    isCollapsed: viewModel.isOnboardingSectionCollapsed(OnboardingSection.gateways.rawValue),
                    onToggle: { viewModel.toggleOnboardingSectionCollapse(OnboardingSection.gateways.rawValue) }
                ) {
                    gatewaysContent
                }
                CollapsibleSectionCard(
                    "Agent Office",
                    subtitle: "Companion memory and personality source",
                    isCollapsed: viewModel.isOnboardingSectionCollapsed(OnboardingSection.agentOffice.rawValue),
                    onToggle: { viewModel.toggleOnboardingSectionCollapse(OnboardingSection.agentOffice.rawValue) }
                ) {
                    agentOfficeContent
                }
                CollapsibleSectionCard(
                    "Generated .env Preview",
                    subtitle: "Review before apply",
                    isCollapsed: viewModel.isOnboardingSectionCollapsed(OnboardingSection.preview.rawValue),
                    onToggle: { viewModel.toggleOnboardingSectionCollapse(OnboardingSection.preview.rawValue) }
                ) {
                    previewContent
                }
                actionRow
            }
            .padding(AppTheme.pagePadding)
        }
    }

    private var progressStripContent: some View {
        HStack(spacing: 10) {
            progressChip("Checks", isDone: viewModel.doctor != nil)
            progressChip("Configuration", isDone: !viewModel.onboarding.phone.isEmpty && !viewModel.onboarding.workspace.isEmpty)
            progressChip("Preview", isDone: !viewModel.envPreview.isEmpty)
            progressChip("Apply", isDone: viewModel.route == .controlPanel)
        }
    }

    private var coreConfigurationContent: some View {
        VStack(alignment: .leading, spacing: AppTheme.fieldSpacing) {
            fieldLabel("Allowed Sender", key: "apple_flow_allowed_senders")
            TextField("Phone (+15551234567)", text: $viewModel.onboarding.phone)
                .textFieldStyle(.roundedBorder)

            fieldLabel("Default Workspace", key: "apple_flow_default_workspace")
            HStack {
                TextField("Workspace (/Users/you/code)", text: $viewModel.onboarding.workspace)
                    .textFieldStyle(.roundedBorder)
                Button("Browse…") {
                    chooseWorkspaceDirectory()
                }
                .buttonStyle(.bordered)
            }

            fieldLabel("Connector", key: "apple_flow_connector")
            Picker("Connector", selection: $viewModel.onboarding.connector) {
                Text("codex-cli").tag("codex-cli")
                Text("claude-cli").tag("claude-cli")
                Text("gemini-cli").tag("gemini-cli")
                Text("kilo-cli").tag("kilo-cli")
                Text("cline").tag("cline")
            }

            fieldLabel("Connector Command", key: "apple_flow_codex_cli_command")
            TextField("Connector command", text: $viewModel.onboarding.connectorCommand)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Run Connector Login in Terminal") {
                    Task { await viewModel.openConnectorAuthTerminal() }
                }
                .buttonStyle(.bordered)

                Text("Use this when connector auth is missing.")
                    .foregroundStyle(AppTheme.subtleText)
                    .font(.caption)
            }
        }
    }

    private var gatewaysContent: some View {
        VStack(alignment: .leading, spacing: AppTheme.fieldSpacing) {
            Toggle("Apple Mail", isOn: $viewModel.onboarding.enableMail)
            if viewModel.onboarding.enableMail {
                TextField("Mail address", text: $viewModel.onboarding.mailAddress)
                    .textFieldStyle(.roundedBorder)
            }

            Toggle("Apple Reminders", isOn: $viewModel.onboarding.enableReminders)
            if viewModel.onboarding.enableReminders {
                fieldLabel("Reminders Task List", key: "apple_flow_reminders_list_name")
                TextField("Reminders list name", text: $viewModel.onboarding.remindersListName)
                    .textFieldStyle(.roundedBorder)
                fieldLabel("Reminders Archive List", key: "apple_flow_reminders_archive_list_name")
                TextField("Reminders archive list name", text: $viewModel.onboarding.remindersArchiveListName)
                    .textFieldStyle(.roundedBorder)
            }

            Toggle("Apple Notes", isOn: $viewModel.onboarding.enableNotes)
            if viewModel.onboarding.enableNotes {
                fieldLabel("Notes Task Folder", key: "apple_flow_notes_folder_name")
                TextField("Notes folder name", text: $viewModel.onboarding.notesFolderName)
                    .textFieldStyle(.roundedBorder)
                fieldLabel("Notes Archive Folder", key: "apple_flow_notes_archive_folder_name")
                TextField("Notes archive folder name", text: $viewModel.onboarding.notesArchiveFolderName)
                    .textFieldStyle(.roundedBorder)
            }

            Toggle("Enable Notes Logging", isOn: $viewModel.onboarding.enableNotesLogging)
            if viewModel.onboarding.enableNotesLogging {
                fieldLabel("Notes Log Folder", key: "apple_flow_notes_log_folder_name")
                TextField("Notes log folder name", text: $viewModel.onboarding.notesLogFolderName)
                    .textFieldStyle(.roundedBorder)
            }

            Toggle("Apple Calendar", isOn: $viewModel.onboarding.enableCalendar)
            if viewModel.onboarding.enableCalendar {
                fieldLabel("Calendar Name", key: "apple_flow_calendar_name")
                TextField("Calendar name", text: $viewModel.onboarding.calendarName)
                    .textFieldStyle(.roundedBorder)
            }
        }
    }

    private var agentOfficeContent: some View {
        VStack(alignment: .leading, spacing: AppTheme.fieldSpacing) {
            HStack(spacing: 8) {
                Toggle("Enable Agent Office Memory", isOn: $viewModel.onboarding.enableAgentOffice)
                Image(systemName: "questionmark.circle")
                    .foregroundStyle(AppTheme.info)
                    .help("""
Agent Office is a structured workspace used by the companion for durable memory and operations.

It contains:
- SOUL.md (identity/personality)
- MEMORY.md (durable memory)
- 00_inbox/, 10_daily/, 20_projects/, 60_memory/, 80_automation/, 90_logs/
- templates/ for daily notes and project briefs
""")
            }
            if viewModel.onboarding.enableAgentOffice {
                Toggle("Create Agent Office scaffold during Apply Setup", isOn: $viewModel.onboarding.createAgentOfficeScaffold)
                    .toggleStyle(.checkbox)
                Text("Runs `agent-office/setup.sh` to create missing folders/files safely (idempotent; does not overwrite existing content).")
                    .foregroundStyle(AppTheme.subtleText)
                    .font(.caption)

                fieldLabel("SOUL File", key: "apple_flow_soul_file")
                TextField("Soul file path", text: $viewModel.onboarding.soulFile)
                    .textFieldStyle(.roundedBorder)
                Text("Sets `apple_flow_enable_memory=true` and writes `apple_flow_soul_file`.")
                    .foregroundStyle(AppTheme.subtleText)
                    .font(.caption)
            }
        }
    }

    private var previewContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Toggle("Show only changed keys", isOn: $viewModel.showPreviewChangesOnly)
                    .toggleStyle(.checkbox)
                Spacer()
                Button("Copy Preview") {
                    viewModel.copyPreviewText()
                }
                .buttonStyle(.bordered)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(viewModel.previewVisibleLines.enumerated()), id: \.offset) { _, line in
                        HStack(alignment: .top, spacing: 10) {
                            Text("\(line.lineNumber)")
                                .foregroundStyle(.secondary)
                                .frame(width: 40, alignment: .trailing)
                            Text(line.text.isEmpty ? " " : line.text)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .font(.system(.caption, design: .monospaced))
                        .padding(.vertical, 1)
                    }
                }
                .textSelection(.enabled)
            }
            .frame(minHeight: 230)
            .padding(8)
            .background(Color.black.opacity(0.22))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    private var actionRow: some View {
        HStack(spacing: 12) {
            Button("Generate Preview") {
                Task { await viewModel.generateEnvPreview() }
            }
            .buttonStyle(.bordered)

            Button("Apply Setup (Write + Validate + Install + Start)") {
                Task { await viewModel.applyOnboarding() }
            }
            .buttonStyle(.borderedProminent)

            Button("Go to Control Board") {
                Task { await viewModel.goToControlBoard() }
            }
            .buttonStyle(.bordered)

            Button("Reset Form") {
                viewModel.resetOnboardingState()
            }
            .buttonStyle(.bordered)
        }
    }

    private func chooseWorkspaceDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        panel.prompt = "Select Workspace"
        panel.message = "Choose the default workspace folder for Apple Flow."
        if panel.runModal() == .OK, let url = panel.url {
            viewModel.onboarding.workspace = url.path
        }
    }

    private func doctorCardContent(_ doctor: WizardDoctorResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            doctorCheckRow("Python available", doctor.pythonOk, remediation: "Install Python 3.11+ and ensure it is available in PATH.")
            doctorCheckRow("Virtual environment exists", doctor.venvOk, remediation: "Run setup script to create `.venv`.")
            doctorCheckRow("Messages DB exists", doctor.messagesDbExists, remediation: "Confirm Messages is set up on this Mac.")
            doctorCheckRow("Messages DB readable", doctor.messagesDbReadable, remediation: "Grant Full Disk Access to terminal/app running Apple Flow.")
            doctorCheckRow("Connector binary found", doctor.connectorBinaryFound, remediation: "Install/auth your connector (`codex login`, `claude auth login`, etc).")
            doctorCheckRow("Admin API token configured", doctor.adminApiTokenPresent, remediation: "Apply setup to auto-generate and persist `apple_flow_admin_api_token`.")

            if !doctor.errors.isEmpty {
                DisclosureGroup("Raw Doctor Errors", isExpanded: $showDoctorErrors) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(doctor.errors, id: \.self) { error in
                            Text("• \(error)")
                                .foregroundStyle(AppTheme.error)
                                .font(.caption)
                        }
                    }
                    .padding(.top, 8)
                }
            }
        }
    }

    private func progressChip(_ title: String, isDone: Bool) -> some View {
        StatusChip(text: title, tone: isDone ? .success : .info)
    }

    private func doctorCheckRow(_ title: String, _ pass: Bool, remediation: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: pass ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(pass ? AppTheme.success : AppTheme.error)
                Text(title)
                    .font(.callout.weight(.medium))
                Spacer()
                StatusChip(text: pass ? "Pass" : "Needs Fix", tone: pass ? .success : .warning)
            }
            if !pass {
                Text(remediation)
                    .font(.caption)
                    .foregroundStyle(AppTheme.subtleText)
                    .padding(.leading, 22)
            }
        }
    }

    @ViewBuilder
    private func fieldLabel(_ label: String, key: String) -> some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.subtleText)
            if let descriptor = viewModel.descriptor(for: key) {
                InlineHelpBadge(descriptor: descriptor)
            }
        }
    }
}
