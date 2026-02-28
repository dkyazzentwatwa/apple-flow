import Foundation
import Security
import AppKit

@MainActor
final class AppViewModel: ObservableObject {
    @Published var route: AppRoute = .loading

    @Published var onboarding = OnboardingState()
    @Published var doctor: WizardDoctorResponse?
    @Published var envPreview = ""
    @Published var showPreviewChangesOnly = false
    @Published var previewDiffKeys: Set<String> = []

    @Published var serviceStatus: ServiceStatusResponse?
    @Published var metrics: MetricsResponse?
    @Published var approvals: [ApprovalItem] = []
    @Published var sessions: [SessionItem] = []
    @Published var events: [AuditEvent] = []

    @Published var logStream = "stderr"
    @Published var logLines = 250
    @Published var logsText = ""
    @Published var isRefreshingControlPanel = false
    @Published var lastRefreshAt: Date?
    @Published var refreshWarnings: [String] = []

    @Published var configValues: [String: String] = [:]
    @Published var configValidationErrors: [String] = []
    @Published var configValidationWarnings: [String] = []
    @Published var configSearchQuery = ""
    @Published var configFilter: ConfigFilterScope = .all
    @Published var revealedSensitiveKeys: Set<String> = []
    @Published var showRestartPrompt = false
    @Published var configSections: [ConfigSectionDescriptor] = []
    @Published var configFields: [ConfigFieldDescriptor] = []
    @Published var collapsedConfigSectionIDs: Set<String> = []
    @Published var collapsedOnboardingSectionIDs: Set<String> = []

    @Published var statusMessage = ""
    @Published var statusTone: StatusTone = .info
    @Published var errorMessage: String?
    @Published var canRetryLastAction = false
    @Published var lastValidationSucceeded: Bool?
    @Published var lastValidationMessage = "Not validated yet"

    private let commandService: CommandServiceProtocol
    private let adminClientFactory: (AdminCredentials) -> AdminApiClientProtocol
    private let envPath: String

    private var adminClient: AdminApiClientProtocol?
    private var hasBootstrapped = false
    private var loadedConfigValues: [String: String] = [:]
    private var serverFieldErrors: [String: String] = [:]
    private var lastAction: RetryableAction?
    private let introSeenKey = "appleFlowApp.introSeen.v1"
    private let configCollapsedSectionsKey = "appleFlowApp.config.collapsedSections.v1"
    private let onboardingCollapsedSectionsKey = "appleFlowApp.onboarding.collapsedSections.v1"

    var editableConfigKeys: [String] {
        configFields.map(\.key)
    }

    var envFilePath: String { envPath }

    var unsavedConfigChangeCount: Int {
        editableConfigKeys.filter { isFieldChanged($0) }.count
    }

    var groupedFilteredConfigDescriptors: [ConfigFieldGroup] {
        let filtered = configFields.filter { descriptor in
            if !configSearchQuery.isEmpty {
                let query = configSearchQuery.lowercased()
                let keyMatch = descriptor.key.lowercased().contains(query)
                let labelMatch = descriptor.label.lowercased().contains(query)
                guard keyMatch || labelMatch else { return false }
            }

            switch configFilter {
            case .all:
                return true
            case .required:
                return descriptor.required
            case .changed:
                return isFieldChanged(descriptor.key)
            case .errors:
                if case .error = validationState(for: descriptor.key) {
                    return true
                }
                return false
            }
        }

        return configSections.sorted { $0.order < $1.order }.compactMap { section in
            let group = filtered.filter { $0.sectionId == section.id }
            if group.isEmpty {
                return nil
            }
            return ConfigFieldGroup(section: section, fields: group)
        }
    }

    var previewVisibleLines: [(lineNumber: Int, text: String)] {
        let lines = envPreview.components(separatedBy: .newlines)
        let filtered = showPreviewChangesOnly ? filterChangedPreviewLines(lines) : lines
        return filtered.enumerated().map { (lineNumber: $0.offset + 1, text: $0.element) }
    }

    init(
        commandService: CommandServiceProtocol = CommandService(),
        adminClientFactory: @escaping (AdminCredentials) -> AdminApiClientProtocol = { creds in
            AdminApiClient(credentials: creds)
        }
    ) {
        self.commandService = commandService
        self.adminClientFactory = adminClientFactory
        self.envPath = commandService.envFilePath
        loadCollapsedState()
    }

    func onAppear() {
        guard !hasBootstrapped else { return }
        hasBootstrapped = true
        if hasSeenIntro {
            Task { await bootstrap() }
        } else {
            route = .intro
            statusMessage = "Read the intro to get started."
            statusTone = .info
        }
    }

    func finishIntroAndContinue() {
        hasSeenIntro = true
        Task { await bootstrap() }
    }

    func skipIntroToControlPanel() async {
        hasSeenIntro = true
        await goToControlBoard()
    }

    func goToControlBoard() async {
        route = .controlPanel
        await refreshControlPanel()
    }

    func returnToConfig() {
        route = .onboarding
        statusMessage = "Returned to setup configuration."
        statusTone = .info
        errorMessage = nil
    }

    func bootstrap() async {
        route = .loading
        statusMessage = "Running environment checks..."
        statusTone = .loading
        errorMessage = nil
        setLastAction(.bootstrap)

        do {
            let doctorResponse = try await commandService.wizardDoctor()
            doctor = doctorResponse
            try? await loadConfigSchema()
            await loadOnboardingDefaults()

            if shouldShowControlPanel(doctor: doctorResponse) {
                route = .controlPanel
                await refreshControlPanel()
                return
            }

            do {
                serviceStatus = try await commandService.serviceStatus()
            } catch {
                errorMessage = error.localizedDescription
            }

            route = .onboarding
            statusMessage = "Complete onboarding checks and setup to continue."
            statusTone = .info
        } catch {
            route = .onboarding
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func generateEnvPreview() async {
        errorMessage = nil
        statusMessage = "Generating .env preview..."
        statusTone = .loading
        setLastAction(.generatePreview)

        do {
            let response = try await commandService.wizardGenerateEnv(onboarding: onboarding)
            if response.ok {
                envPreview = response.envPreview
                computePreviewDiff()
                statusMessage = "Review the generated .env preview."
                statusTone = .success
            } else {
                statusTone = .error
                errorMessage = (response.validationErrors + (response.errors ?? [])).joined(separator: "\n")
            }
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func applyOnboarding() async {
        errorMessage = nil
        statusMessage = "Applying onboarding configuration..."
        statusTone = .loading
        setLastAction(.applyOnboarding)

        do {
            if envPreview.isEmpty {
                await generateEnvPreview()
                if envPreview.isEmpty {
                    return
                }
            }

            var setMap = parseSetValues(from: envPreview)
            let existingToken = setMap["apple_flow_admin_api_token", default: ""].trimmingCharacters(in: .whitespaces)
            if existingToken.isEmpty {
                setMap["apple_flow_admin_api_token"] = generateAdminToken()
            }
            if onboarding.enableAgentOffice {
                if onboarding.createAgentOfficeScaffold {
                    try await commandService.createAgentOfficeScaffold()
                }
                setMap["apple_flow_enable_memory"] = "true"
                setMap["apple_flow_soul_file"] = onboarding.soulFile
            }

            let setValues = setMap.keys.sorted().compactMap { key -> String? in
                guard let value = setMap[key] else { return nil }
                return "\(key)=\(value)"
            }

            let write = try await commandService.configWrite(setValues: setValues)
            guard write.ok else {
                throw AppViewError.commandFailed(write.errors.joined(separator: "\n"))
            }

            let gatewayResponse = try await commandService.wizardEnsureGateways(onboarding: onboarding)
            if !gatewayResponse.ok {
                let details = (gatewayResponse.errors ?? ["Gateway setup failed"]).joined(separator: "\n")
                throw AppViewError.commandFailed(details)
            }

            let validate = try await commandService.configValidate()
            applyValidateResponse(validate)
            if !validate.ok {
                throw AppViewError.commandFailed(validate.errors.joined(separator: "\n"))
            }

            let install = try await commandService.serviceInstall()
            if !install.ok {
                throw AppViewError.commandFailed((install.errors ?? ["Service install failed"]).joined(separator: "\n"))
            }

            let start = try await commandService.serviceStart()
            if !start.ok {
                throw AppViewError.commandFailed((start.errors ?? ["Service start failed"]).joined(separator: "\n"))
            }

            statusMessage = "Onboarding complete. Loading control panel..."
            statusTone = .success
            await bootstrap()
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func openConnectorAuthTerminal() async {
        let command: String
        switch onboarding.connector {
        case "claude-cli":
            command = "claude auth login"
        case "gemini-cli":
            command = "gemini auth login"
        case "kilo-cli":
            command = "kilo auth login"
        case "cline":
            command = "cline auth"
        default:
            command = "codex login"
        }

        do {
            try await commandService.openTerminal(command: command)
            statusMessage = "Opened Terminal to run: \(command)"
            statusTone = .success
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func refreshControlPanel() async {
        guard !isRefreshingControlPanel else { return }
        isRefreshingControlPanel = true
        defer { isRefreshingControlPanel = false }

        statusMessage = "Refreshing control panel..."
        statusTone = .loading
        setLastAction(.refreshControlPanel)
        refreshWarnings = []
        var warnings: [String] = []

        do {
            serviceStatus = try await commandService.serviceStatus()
        } catch {
            warnings.append("Service status: \(error.localizedDescription)")
        }

        do {
            try await loadConfigSchema()
        } catch {
            warnings.append("Config schema: \(error.localizedDescription)")
        }

        do {
            try await loadConfigEditorValues()
        } catch {
            warnings.append("Config values: \(error.localizedDescription)")
        }

        do {
            try configureAdminClient()
            try await refreshAdminData()
        } catch {
            warnings.append("Admin API data: \(error.localizedDescription)")
        }

        do {
            try await refreshLogsInternal()
        } catch {
            warnings.append("Logs: \(error.localizedDescription)")
        }

        lastRefreshAt = Date()
        refreshWarnings = warnings

        if warnings.isEmpty {
            errorMessage = nil
            statusMessage = "Control panel refreshed."
            statusTone = .success
            return
        }

        errorMessage = nil
        statusMessage = "Control panel refreshed with \(warnings.count) warning\(warnings.count == 1 ? "" : "s")."
        statusTone = .warning
    }

    func installService() async {
        await runServiceAction(.installService, "Installing service", action: commandService.serviceInstall)
    }

    func startService() async {
        await runServiceAction(.startService, "Starting service", action: commandService.serviceStart)
    }

    func stopService() async {
        await runServiceAction(.stopService, "Stopping service", action: commandService.serviceStop)
    }

    func restartService() async {
        await runServiceAction(.restartService, "Restarting service", action: commandService.serviceRestart)
    }

    func restartServiceStopStart() async {
        errorMessage = nil
        statusMessage = "Restarting service (stop/start)..."
        statusTone = .loading
        setLastAction(.restartServiceStopStart)

        var stopError: String?
        do {
            let stopResponse = try await commandService.serviceStop()
            if !stopResponse.ok {
                stopError = (stopResponse.errors ?? ["Failed to stop service."]).joined(separator: "\n")
            }
        } catch {
            stopError = error.localizedDescription
        }

        do {
            let startResponse = try await commandService.serviceStart()
            if !startResponse.ok {
                throw AppViewError.commandFailed((startResponse.errors ?? ["Failed to start service."]).joined(separator: "\n"))
            }
        } catch {
            statusTone = .error
            if let stopError {
                errorMessage = "Stop error: \(stopError)\nStart error: \(error.localizedDescription)"
            } else {
                errorMessage = error.localizedDescription
            }
            return
        }

        await refreshControlPanel()
        if let stopError {
            statusTone = .warning
            statusMessage = "Restarted with warning."
            errorMessage = "Stop warning: \(stopError)"
        } else {
            statusTone = .success
            statusMessage = "Service restarted via stop/start."
        }
    }

    func approve(_ requestID: String) async {
        setLastAction(.approve(requestID))
        await overrideApproval(requestID: requestID, status: "approved")
    }

    func deny(_ requestID: String) async {
        setLastAction(.deny(requestID))
        await overrideApproval(requestID: requestID, status: "denied")
    }

    func refreshLogs() async {
        setLastAction(.refreshLogs)
        do {
            _ = try await refreshLogsInternal()
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func clearErrorMessage() {
        errorMessage = nil
    }

    func copyErrorMessage() {
        guard let errorMessage, !errorMessage.isEmpty else { return }
        #if canImport(AppKit)
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(errorMessage, forType: .string)
        #endif
        statusMessage = "Copied error details."
        statusTone = .info
    }

    func retryLastAction() {
        guard let action = lastAction else { return }
        Task {
            switch action {
            case .bootstrap:
                await bootstrap()
            case .generatePreview:
                await generateEnvPreview()
            case .applyOnboarding:
                await applyOnboarding()
            case .refreshControlPanel:
                await refreshControlPanel()
            case .validateConfig:
                await validateConfigOnly()
            case .applyConfigValidateRestart:
                await applyConfigValidateAndRestart()
            case .refreshLogs:
                await refreshLogs()
            case .installService:
                await installService()
            case .startService:
                await startService()
            case .stopService:
                await stopService()
            case .restartService:
                await restartService()
            case .restartServiceStopStart:
                await restartServiceStopStart()
            case .approve(let requestID):
                await approve(requestID)
            case .deny(let requestID):
                await deny(requestID)
            }
        }
    }

    func resetOnboardingState() {
        onboarding = OnboardingState()
        envPreview = ""
        previewDiffKeys = []
        showPreviewChangesOnly = false
        errorMessage = nil
        configValidationErrors = []
        configValidationWarnings = []
        statusMessage = "Onboarding form reset."
        statusTone = .info

        Task {
            await loadOnboardingDefaults()
        }
    }

    func applyConfigValidateAndRestart() async {
        errorMessage = nil
        statusMessage = "Applying config updates..."
        statusTone = .loading
        setLastAction(.applyConfigValidateRestart)

        let setValues = editableConfigKeys.compactMap { key -> String? in
            guard let value = configValues[key] else { return nil }
            return "\(key)=\(value)"
        }

        do {
            let write = try await commandService.configWrite(setValues: setValues)
            if !write.ok {
                throw AppViewError.commandFailed(write.errors.joined(separator: "\n"))
            }

            let validate = try await commandService.configValidate()
            applyValidateResponse(validate)
            if !validate.ok {
                throw AppViewError.commandFailed(validate.errors.joined(separator: "\n"))
            }

            await refreshControlPanel()
            showRestartPrompt = true
            statusMessage = "Config applied and validated. Restart recommended."
            statusTone = .success
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func validateConfigOnly() async {
        errorMessage = nil
        statusMessage = "Validating configuration..."
        statusTone = .loading
        setLastAction(.validateConfig)

        do {
            let validate = try await commandService.configValidate()
            applyValidateResponse(validate)
            if validate.ok {
                statusMessage = "Configuration validated successfully."
                statusTone = .success
            } else {
                throw AppViewError.commandFailed(validate.errors.joined(separator: "\n"))
            }
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    func resetConfigValue(for key: String) {
        configValues[key] = loadedConfigValues[key, default: ""]
    }

    func revertAllConfigChanges() {
        configValues = loadedConfigValues
        revealedSensitiveKeys.removeAll()
        configValidationErrors = []
        configValidationWarnings = []
        serverFieldErrors = [:]
        lastValidationSucceeded = nil
        lastValidationMessage = "Reverted to loaded .env values."
        statusMessage = "Config changes reverted."
        statusTone = .info
    }

    func isConfigSectionCollapsed(_ sectionID: String) -> Bool {
        collapsedConfigSectionIDs.contains(sectionID)
    }

    func toggleConfigSectionCollapse(_ sectionID: String) {
        if collapsedConfigSectionIDs.contains(sectionID) {
            collapsedConfigSectionIDs.remove(sectionID)
        } else {
            collapsedConfigSectionIDs.insert(sectionID)
        }
        persistCollapsedState()
    }

    func collapseAllConfigSections() {
        collapsedConfigSectionIDs = Set(configSections.map(\.id))
        persistCollapsedState()
    }

    func expandAllConfigSections() {
        collapsedConfigSectionIDs.removeAll()
        persistCollapsedState()
    }

    func isOnboardingSectionCollapsed(_ sectionID: String) -> Bool {
        collapsedOnboardingSectionIDs.contains(sectionID)
    }

    func toggleOnboardingSectionCollapse(_ sectionID: String) {
        if collapsedOnboardingSectionIDs.contains(sectionID) {
            collapsedOnboardingSectionIDs.remove(sectionID)
        } else {
            collapsedOnboardingSectionIDs.insert(sectionID)
        }
        persistCollapsedState()
    }

    func collapseAllOnboardingSections() {
        collapsedOnboardingSectionIDs = Set(OnboardingSection.allCases.map(\.rawValue))
        collapsedOnboardingSectionIDs.remove(OnboardingSection.core.rawValue)
        persistCollapsedState()
    }

    func expandAllOnboardingSections() {
        collapsedOnboardingSectionIDs.removeAll()
        persistCollapsedState()
    }

    func isFieldChanged(_ key: String) -> Bool {
        configValues[key, default: ""] != loadedConfigValues[key, default: ""]
    }

    func descriptor(for key: String) -> ConfigFieldDescriptor? {
        configFields.first(where: { $0.key == key })
    }

    func isSensitiveRevealed(_ key: String) -> Bool {
        revealedSensitiveKeys.contains(key)
    }

    func toggleSensitiveReveal(_ key: String) {
        if revealedSensitiveKeys.contains(key) {
            revealedSensitiveKeys.remove(key)
        } else {
            revealedSensitiveKeys.insert(key)
        }
    }

    func validationState(for key: String) -> FieldValidationState {
        if let serverError = serverFieldErrors[key], !serverError.isEmpty {
            return .error(serverError)
        }

        guard let descriptor = descriptor(for: key) else {
            return .neutral
        }

        let value = configValues[key, default: ""]
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)

        if descriptor.required && trimmed.isEmpty {
            return .error("Required")
        }

        switch descriptor.inputType {
        case .number:
            if !trimmed.isEmpty && Int(trimmed) == nil {
                return .error("Must be a number")
            }
        case .bool:
            if !trimmed.isEmpty {
                let lower = trimmed.lowercased()
                if lower != "true" && lower != "false" {
                    return .error("Use true or false")
                }
            }
        case .token:
            if descriptor.required && trimmed.isEmpty {
                return .error("Token required")
            }
        case .path:
            if descriptor.required && trimmed.isEmpty {
                return .error("Path required")
            }
        case .csv, .text:
            break
        }

        if isFieldChanged(key) && !trimmed.isEmpty {
            return .valid
        }

        return .neutral
    }

    func copyPreviewText() {
        guard !envPreview.isEmpty else { return }
        #if canImport(AppKit)
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(envPreview, forType: .string)
        #endif
        statusMessage = "Copied generated .env preview."
        statusTone = .info
    }

    private func shouldShowControlPanel(doctor: WizardDoctorResponse) -> Bool {
        doctor.ok && doctor.messagesDbReadable && doctor.connectorBinaryFound && doctor.adminApiTokenPresent
    }

    private func parseSetValues(from envPreview: String) -> [String: String] {
        var map: [String: String] = [:]
        envPreview
            .split(separator: "\n")
            .map(String.init)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && !$0.hasPrefix("#") && $0.contains("=") }
            .forEach { line in
                let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
                guard parts.count == 2 else { return }
                map[parts[0]] = parts[1]
            }
        return map
    }

    private func generateAdminToken() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        if SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess {
            return bytes.map { String(format: "%02x", $0) }.joined()
        }
        return UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    }

    private func loadOnboardingDefaults() async {
        do {
            let response = try await commandService.configRead(keys: [
                "apple_flow_allowed_senders",
                "apple_flow_allowed_workspaces",
                "apple_flow_connector",
                "apple_flow_codex_cli_command",
                "apple_flow_claude_cli_command",
                "apple_flow_cline_command",
                "apple_flow_reminders_list_name",
                "apple_flow_reminders_archive_list_name",
                "apple_flow_notes_folder_name",
                "apple_flow_notes_archive_folder_name",
                "apple_flow_notes_log_folder_name",
                "apple_flow_calendar_name",
                "apple_flow_enable_memory",
                "apple_flow_soul_file",
                "apple_flow_admin_api_token",
            ], effective: false)
            if !response.ok {
                return
            }

            loadedConfigValues.merge(response.values) { _, new in new }

            if let phone = response.values["apple_flow_allowed_senders"], !phone.isEmpty {
                onboarding.phone = phone
            }
            if let workspace = response.values["apple_flow_allowed_workspaces"], !workspace.isEmpty {
                onboarding.workspace = workspace.split(separator: ",").first.map(String.init) ?? workspace
            }
            if let connector = response.values["apple_flow_connector"], !connector.isEmpty {
                onboarding.connector = connector
            }

            switch onboarding.connector {
            case "claude-cli":
                onboarding.connectorCommand = response.values["apple_flow_claude_cli_command"] ?? "claude"
            case "gemini-cli":
                onboarding.connectorCommand = response.values["apple_flow_gemini_cli_command"] ?? "gemini"
            case "kilo-cli":
                onboarding.connectorCommand = response.values["apple_flow_kilo_cli_command"] ?? "kilo"
            case "cline":
                onboarding.connectorCommand = response.values["apple_flow_cline_command"] ?? "cline"
            default:
                onboarding.connectorCommand = response.values["apple_flow_codex_cli_command"] ?? "codex"
            }

            if let value = response.values["apple_flow_reminders_list_name"], !value.isEmpty {
                onboarding.remindersListName = value
            }
            if let value = response.values["apple_flow_reminders_archive_list_name"], !value.isEmpty {
                onboarding.remindersArchiveListName = value
            }
            if let value = response.values["apple_flow_notes_folder_name"], !value.isEmpty {
                onboarding.notesFolderName = value
            }
            if let value = response.values["apple_flow_notes_archive_folder_name"], !value.isEmpty {
                onboarding.notesArchiveFolderName = value
            }
            if let value = response.values["apple_flow_notes_log_folder_name"], !value.isEmpty {
                onboarding.notesLogFolderName = value
            }
            if let value = response.values["apple_flow_calendar_name"], !value.isEmpty {
                onboarding.calendarName = value
            }
            if let value = response.values["apple_flow_enable_memory"], !value.isEmpty {
                onboarding.enableAgentOffice = value.lowercased() == "true"
            }
            if let value = response.values["apple_flow_soul_file"], !value.isEmpty {
                onboarding.soulFile = value
            }
        } catch {
            // Non-fatal; onboarding can continue with defaults.
        }
    }

    private func loadConfigEditorValues() async throws {
        let response = try await commandService.configRead(keys: editableConfigKeys, effective: true)
        if !response.ok {
            throw AppViewError.commandFailed((response.errors ?? ["config read failed"]).joined(separator: "\n"))
        }
        configValues = response.values
        loadedConfigValues = response.values
        serverFieldErrors = [:]
    }

    private func configureAdminClient() throws {
        let host = configValues["apple_flow_admin_host", default: "127.0.0.1"]
        let portRaw = configValues["apple_flow_admin_port", default: "8787"]
        guard let port = Int(portRaw) else {
            throw AppViewError.commandFailed("apple_flow_admin_port must be a number")
        }
        let token = configValues["apple_flow_admin_api_token", default: ""]
        if token.isEmpty {
            throw AppViewError.commandFailed("apple_flow_admin_api_token is required")
        }
        adminClient = adminClientFactory(AdminCredentials(host: host, port: port, token: token))
    }

    private func refreshAdminData() async throws {
        guard let client = adminClient else {
            throw AppViewError.commandFailed("Admin client not initialized")
        }
        metrics = try await client.metrics()
        sessions = try await client.sessions()
        approvals = try await client.approvals()
        events = try await client.events(limit: 200)
    }

    @discardableResult
    private func refreshLogsInternal() async throws -> ServiceLogsResponse {
        let response = try await commandService.serviceLogs(stream: logStream, lines: logLines)
        if !response.ok {
            throw AppViewError.commandFailed((response.errors ?? ["log read failed"]).joined(separator: "\n"))
        }
        logsText = response.lines.joined(separator: "\n")
        return response
    }

    private func runServiceAction(
        _ action: RetryableAction,
        _ message: String,
        action command: () async throws -> ServiceActionResponse
    ) async {
        errorMessage = nil
        statusMessage = message
        statusTone = .loading
        setLastAction(action)
        do {
            let response = try await command()
            if !response.ok {
                throw AppViewError.commandFailed((response.errors ?? ["Service action failed"]).joined(separator: "\n"))
            }
            await refreshControlPanel()
            statusTone = .success
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    private func overrideApproval(requestID: String, status: String) async {
        guard let client = adminClient else {
            statusTone = .error
            errorMessage = "Admin client not configured"
            return
        }
        do {
            _ = try await client.overrideApproval(requestID: requestID, status: status)
            try await refreshAdminData()
            statusMessage = "Approval \(status)."
            statusTone = .success
        } catch {
            statusTone = .error
            errorMessage = error.localizedDescription
        }
    }

    private func setLastAction(_ action: RetryableAction) {
        lastAction = action
        canRetryLastAction = true
    }

    private func applyValidateResponse(_ validate: ConfigValidateResponse) {
        configValidationErrors = validate.errors
        configValidationWarnings = validate.warnings
        lastValidationSucceeded = validate.ok
        lastValidationMessage = validate.ok ? "Validated successfully" : "Validation failed"
        serverFieldErrors = buildServerFieldErrors(from: validate.errors)
    }

    private func buildServerFieldErrors(from errors: [String]) -> [String: String] {
        guard !errors.isEmpty else { return [:] }
        var result: [String: String] = [:]
        for descriptor in configFields {
            let full = descriptor.key.lowercased()
            let short = descriptor.key.replacingOccurrences(of: "apple_flow_", with: "").lowercased()
            if let match = errors.first(where: { error in
                let lower = error.lowercased()
                return lower.contains(full) || lower.contains(short)
            }) {
                result[descriptor.key] = match
            }
        }
        return result
    }

    private func computePreviewDiff() {
        let previewMap = parseSetValues(from: envPreview)
        var diffKeys: Set<String> = []
        for (key, value) in previewMap {
            let existing = loadedConfigValues[key, default: ""]
            if existing != value {
                diffKeys.insert(key)
            }
        }
        previewDiffKeys = diffKeys
    }

    private func filterChangedPreviewLines(_ lines: [String]) -> [String] {
        lines.filter { line in
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#"), trimmed.contains("=") else {
                return false
            }
            let key = trimmed.split(separator: "=", maxSplits: 1).first.map(String.init) ?? ""
            return previewDiffKeys.contains(key)
        }
    }

    private var hasSeenIntro: Bool {
        get { UserDefaults.standard.bool(forKey: introSeenKey) }
        set { UserDefaults.standard.set(newValue, forKey: introSeenKey) }
    }

    private func loadConfigSchema() async throws {
        let response = try await commandService.configSchema()
        if !response.ok {
            throw AppViewError.commandFailed((response.errors ?? ["config schema failed"]).joined(separator: "\n"))
        }
        configSections = response.sections
        configFields = response.fields
        applySectionDefaultsIfNeeded()
    }

    private func loadCollapsedState() {
        let defaults = UserDefaults.standard
        let configCollapsed = defaults.array(forKey: configCollapsedSectionsKey) as? [String] ?? []
        let onboardingCollapsed = defaults.array(forKey: onboardingCollapsedSectionsKey) as? [String] ?? []
        collapsedConfigSectionIDs = Set(configCollapsed)
        if onboardingCollapsed.isEmpty {
            collapsedOnboardingSectionIDs = Set(OnboardingSection.allCases.map(\.rawValue))
            collapsedOnboardingSectionIDs.remove(OnboardingSection.core.rawValue)
        } else {
            collapsedOnboardingSectionIDs = Set(onboardingCollapsed)
        }
    }

    private func persistCollapsedState() {
        let defaults = UserDefaults.standard
        defaults.set(Array(collapsedConfigSectionIDs), forKey: configCollapsedSectionsKey)
        defaults.set(Array(collapsedOnboardingSectionIDs), forKey: onboardingCollapsedSectionsKey)
    }

    private func applySectionDefaultsIfNeeded() {
        if collapsedConfigSectionIDs.isEmpty {
            let collapsed = configSections.filter { !$0.defaultExpanded }.map(\.id)
            collapsedConfigSectionIDs = Set(collapsed)
            persistCollapsedState()
        }
        if collapsedOnboardingSectionIDs.isEmpty {
            collapsedOnboardingSectionIDs = Set(OnboardingSection.allCases.map(\.rawValue))
            collapsedOnboardingSectionIDs.remove(OnboardingSection.core.rawValue)
            persistCollapsedState()
        }
    }
}

private enum RetryableAction {
    case bootstrap
    case generatePreview
    case applyOnboarding
    case refreshControlPanel
    case validateConfig
    case applyConfigValidateRestart
    case refreshLogs
    case installService
    case startService
    case stopService
    case restartService
    case restartServiceStopStart
    case approve(String)
    case deny(String)
}

enum OnboardingSection: String, CaseIterable {
    case progress
    case checks
    case core
    case gateways
    case agentOffice
    case preview
}
