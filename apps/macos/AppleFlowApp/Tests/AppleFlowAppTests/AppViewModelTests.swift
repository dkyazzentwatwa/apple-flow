import XCTest
@testable import AppleFlowApp

final class AppViewModelTests: XCTestCase {
    @MainActor
    func testDescriptorCatalogCoversEditableKeys() async {
        let command = MockCommandService()
        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }

        let editable = Set(viewModel.editableConfigKeys)
        let described = Set(ConfigFieldCatalog.all.map(\.key))

        XCTAssertEqual(editable, described)
    }

    @MainActor
    func testDirtyTrackingChangedAndReverted() async {
        let command = MockCommandService()
        command.configReadResponse = ConfigReadResponse(ok: true, values: [
            "apple_flow_admin_host": "127.0.0.1",
            "apple_flow_admin_port": "8787",
            "apple_flow_admin_api_token": "token",
            "apple_flow_allowed_senders": "+15551234567",
            "apple_flow_allowed_workspaces": "/Users/test/code",
            "apple_flow_default_workspace": "/Users/test/code",
            "apple_flow_connector": "codex-cli",
            "apple_flow_codex_cli_command": "codex",
            "apple_flow_claude_cli_command": "claude",
            "apple_flow_cline_command": "cline",
            "apple_flow_reminders_list_name": "agent-task",
            "apple_flow_reminders_archive_list_name": "agent-archive",
            "apple_flow_notes_folder_name": "agent-task",
            "apple_flow_notes_archive_folder_name": "agent-archive",
            "apple_flow_notes_log_folder_name": "agent-logs",
            "apple_flow_calendar_name": "agent-schedule",
            "apple_flow_enable_memory": "false",
            "apple_flow_soul_file": "agent-office/SOUL.md",
        ], errors: nil)

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        await viewModel.refreshControlPanel()

        XCTAssertEqual(viewModel.unsavedConfigChangeCount, 0)
        viewModel.configValues["apple_flow_admin_port"] = "9000"
        XCTAssertTrue(viewModel.isFieldChanged("apple_flow_admin_port"))
        XCTAssertGreaterThan(viewModel.unsavedConfigChangeCount, 0)

        viewModel.resetConfigValue(for: "apple_flow_admin_port")
        XCTAssertFalse(viewModel.isFieldChanged("apple_flow_admin_port"))
        XCTAssertEqual(viewModel.unsavedConfigChangeCount, 0)
    }

    @MainActor
    func testClientValidationFlagsInvalidAdminPortAndBool() async {
        let command = MockCommandService()
        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        viewModel.configValues["apple_flow_admin_port"] = "not-a-number"
        viewModel.configValues["apple_flow_enable_memory"] = "maybe"

        let adminState = viewModel.validationState(for: "apple_flow_admin_port")
        let memoryState = viewModel.validationState(for: "apple_flow_enable_memory")

        XCTAssertEqual(adminState, .error("Must be a number"))
        XCTAssertEqual(memoryState, .error("Use true or false"))
    }

    @MainActor
    func testTokenMaskRevealToggleState() async {
        let command = MockCommandService()
        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }

        XCTAssertFalse(viewModel.isSensitiveRevealed("apple_flow_admin_api_token"))
        viewModel.toggleSensitiveReveal("apple_flow_admin_api_token")
        XCTAssertTrue(viewModel.isSensitiveRevealed("apple_flow_admin_api_token"))
        viewModel.toggleSensitiveReveal("apple_flow_admin_api_token")
        XCTAssertFalse(viewModel.isSensitiveRevealed("apple_flow_admin_api_token"))
    }

    @MainActor
    func testBootstrapRoutesToControlPanelWhenDoctorPasses() async {
        let command = MockCommandService()
        command.doctorResponse = WizardDoctorResponse(
            ok: true,
            pythonOk: true,
            venvOk: true,
            messagesDbExists: true,
            messagesDbReadable: true,
            connectorBinaryFound: true,
            connectorBinaryPath: "/usr/local/bin/codex",
            adminApiTokenPresent: true,
            errors: []
        )
        command.serviceStatusResponse = ServiceStatusResponse(
            ok: true,
            launchdLoaded: true,
            launchdPid: 123,
            daemonProcessDetected: true,
            plistPath: "~/Library/LaunchAgents/local.apple-flow.plist",
            healthy: true,
            errors: nil
        )
        command.configReadResponse = ConfigReadResponse(ok: true, values: [
            "apple_flow_admin_host": "127.0.0.1",
            "apple_flow_admin_port": "8787",
            "apple_flow_admin_api_token": "token",
        ], errors: nil)

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        await viewModel.bootstrap()

        XCTAssertEqual(viewModel.route, .controlPanel)
    }

    @MainActor
    func testBootstrapRoutesToOnboardingWhenDoctorFails() async {
        let command = MockCommandService()
        command.doctorResponse = WizardDoctorResponse(
            ok: true,
            pythonOk: true,
            venvOk: true,
            messagesDbExists: true,
            messagesDbReadable: false,
            connectorBinaryFound: false,
            connectorBinaryPath: "",
            adminApiTokenPresent: false,
            errors: ["missing token"]
        )

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        await viewModel.bootstrap()

        XCTAssertEqual(viewModel.route, .onboarding)
    }

    @MainActor
    func testGenerateEnvPreviewUpdatesPreviewText() async {
        let command = MockCommandService()
        command.generateEnvResponse = WizardGenerateEnvResponse(
            ok: true,
            envPreview: "apple_flow_allowed_senders=+15551234567",
            validationErrors: [],
            errors: nil
        )

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        viewModel.onboarding.phone = "+15551234567"
        viewModel.onboarding.workspace = "/Users/test/code"

        await viewModel.generateEnvPreview()

        XCTAssertTrue(viewModel.envPreview.contains("apple_flow_allowed_senders"))
    }

    @MainActor
    func testBootstrapPreservesDoctorChecksWhenServiceStatusFails() async {
        let command = MockCommandService()
        command.doctorResponse = WizardDoctorResponse(
            ok: true,
            pythonOk: true,
            venvOk: true,
            messagesDbExists: true,
            messagesDbReadable: true,
            connectorBinaryFound: true,
            connectorBinaryPath: "/usr/local/bin/codex",
            adminApiTokenPresent: false,
            errors: ["apple_flow_admin_api_token is missing"]
        )
        command.serviceStatusError = AppViewError.commandFailed("service status failed")

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        await viewModel.bootstrap()

        XCTAssertEqual(viewModel.route, .onboarding)
        XCTAssertNotNil(viewModel.doctor)
        XCTAssertEqual(viewModel.doctor?.adminApiTokenPresent, false)
    }

    @MainActor
    func testApplyConfigValidateAndRestartInvokesRestart() async {
        let command = MockCommandService()
        command.configWriteResponse = ConfigWriteResponse(ok: true, updatedKeys: ["a"], errors: [], code: nil)
        command.configValidateResponse = ConfigValidateResponse(ok: true, errors: [], warnings: [], code: nil)
        command.serviceActionResponse = ServiceActionResponse(ok: true, label: "local.apple-flow", plistPath: nil, pythonBin: nil, errors: nil, code: nil)
        command.serviceStatusResponse = ServiceStatusResponse(ok: true, launchdLoaded: true, launchdPid: 1, daemonProcessDetected: true, plistPath: "plist", healthy: true, errors: nil)
        command.configReadResponse = ConfigReadResponse(ok: true, values: [
            "apple_flow_admin_host": "127.0.0.1",
            "apple_flow_admin_port": "8787",
            "apple_flow_admin_api_token": "token",
        ], errors: nil)

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        viewModel.configValues = [
            "apple_flow_allowed_senders": "+15551234567",
            "apple_flow_allowed_workspaces": "/Users/test/code",
            "apple_flow_default_workspace": "/Users/test/code",
            "apple_flow_connector": "codex-cli",
            "apple_flow_codex_cli_command": "codex",
            "apple_flow_claude_cli_command": "claude",
            "apple_flow_cline_command": "cline",
            "apple_flow_admin_host": "127.0.0.1",
            "apple_flow_admin_port": "8787",
            "apple_flow_admin_api_token": "token",
        ]

        await viewModel.applyConfigValidateAndRestart()

        XCTAssertEqual(command.serviceRestartCallCount, 1)
    }

    @MainActor
    func testApplyOnboardingCreatesAgentOfficeScaffoldWhenEnabled() async {
        let command = MockCommandService()
        command.generateEnvResponse = WizardGenerateEnvResponse(
            ok: true,
            envPreview: """
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/test/code
apple_flow_default_workspace=/Users/test/code
apple_flow_connector=codex-cli
apple_flow_codex_cli_command=codex
apple_flow_admin_host=127.0.0.1
apple_flow_admin_port=8787
apple_flow_admin_api_token=
""",
            validationErrors: [],
            errors: nil
        )
        command.configWriteResponse = ConfigWriteResponse(ok: true, updatedKeys: ["a"], errors: [], code: nil)
        command.ensureGatewaysResponse = WizardEnsureGatewaysResponse(ok: true, results: [], errors: nil)
        command.configValidateResponse = ConfigValidateResponse(ok: true, errors: [], warnings: [], code: nil)
        command.serviceActionResponse = ServiceActionResponse(ok: true, label: "local.apple-flow", plistPath: nil, pythonBin: nil, errors: nil, code: nil)
        command.doctorResponse = WizardDoctorResponse(
            ok: true,
            pythonOk: true,
            venvOk: true,
            messagesDbExists: true,
            messagesDbReadable: true,
            connectorBinaryFound: true,
            connectorBinaryPath: "/usr/local/bin/codex",
            adminApiTokenPresent: true,
            errors: []
        )
        command.serviceStatusResponse = ServiceStatusResponse(
            ok: true, launchdLoaded: true, launchdPid: 1, daemonProcessDetected: true, plistPath: "plist", healthy: true, errors: nil
        )
        command.configReadResponse = ConfigReadResponse(ok: true, values: [
            "apple_flow_admin_host": "127.0.0.1",
            "apple_flow_admin_port": "8787",
            "apple_flow_admin_api_token": "token",
        ], errors: nil)

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        viewModel.onboarding.enableAgentOffice = true
        viewModel.onboarding.createAgentOfficeScaffold = true
        viewModel.onboarding.phone = "+15551234567"
        viewModel.onboarding.workspace = "/Users/test/code"

        await viewModel.applyOnboarding()

        XCTAssertEqual(command.createAgentOfficeScaffoldCallCount, 1)
    }

    @MainActor
    func testGoToControlBoardRoutesAndRefreshes() async {
        let command = MockCommandService()
        command.configReadResponse = ConfigReadResponse(
            ok: true,
            values: [
                "apple_flow_admin_host": "127.0.0.1",
                "apple_flow_admin_port": "8787",
                "apple_flow_admin_api_token": "token",
            ],
            errors: nil
        )
        command.logsResponse = ServiceLogsResponse(ok: true, path: "/tmp/log", lines: ["line-1"], errors: nil)

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }

        await viewModel.goToControlBoard()

        XCTAssertEqual(viewModel.route, .controlPanel)
        XCTAssertNotNil(viewModel.lastRefreshAt)
        XCTAssertEqual(viewModel.logsText, "line-1")
    }

    @MainActor
    func testReturnToConfigRoutesToOnboarding() async {
        let command = MockCommandService()
        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }
        viewModel.route = .controlPanel

        viewModel.returnToConfig()

        XCTAssertEqual(viewModel.route, .onboarding)
        if case .info = viewModel.statusTone {} else {
            XCTFail("Expected info status tone")
        }
        XCTAssertEqual(viewModel.statusMessage, "Returned to setup configuration.")
    }

    @MainActor
    func testRefreshControlPanelCollectsWarningsAndContinues() async {
        let command = MockCommandService()
        command.serviceStatusError = AppViewError.commandFailed("service status failed")
        command.logsError = AppViewError.commandFailed("logs unavailable")
        command.configReadResponse = ConfigReadResponse(
            ok: true,
            values: [
                "apple_flow_admin_host": "127.0.0.1",
                "apple_flow_admin_port": "8787",
                "apple_flow_admin_api_token": "token",
            ],
            errors: nil
        )

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }

        await viewModel.refreshControlPanel()

        if case .warning = viewModel.statusTone {} else {
            XCTFail("Expected warning status tone")
        }
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertEqual(viewModel.refreshWarnings.count, 2)
        XCTAssertNotNil(viewModel.metrics)
        XCTAssertNotNil(viewModel.lastRefreshAt)
    }

    @MainActor
    func testRefreshControlPanelPreventsOverlapWhileInFlight() async {
        let command = MockCommandService()
        command.serviceStatusDelayNanoseconds = 60_000_000
        command.configReadResponse = ConfigReadResponse(
            ok: true,
            values: [
                "apple_flow_admin_host": "127.0.0.1",
                "apple_flow_admin_port": "8787",
                "apple_flow_admin_api_token": "token",
            ],
            errors: nil
        )

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }

        let firstRefresh = Task { await viewModel.refreshControlPanel() }
        try? await Task.sleep(nanoseconds: 10_000_000)
        XCTAssertTrue(viewModel.isRefreshingControlPanel)

        await viewModel.refreshControlPanel()
        await firstRefresh.value

        XCTAssertFalse(viewModel.isRefreshingControlPanel)
        XCTAssertEqual(command.serviceStatusCallCount, 1)
    }

    @MainActor
    func testRefreshControlPanelSuccessClearsWarningsAndUpdatesTimestamp() async {
        let command = MockCommandService()
        command.configReadResponse = ConfigReadResponse(
            ok: true,
            values: [
                "apple_flow_admin_host": "127.0.0.1",
                "apple_flow_admin_port": "8787",
                "apple_flow_admin_api_token": "token",
            ],
            errors: nil
        )
        command.logsError = AppViewError.commandFailed("log stream unavailable")

        let viewModel = AppViewModel(commandService: command) { _ in MockAdminClient() }

        await viewModel.refreshControlPanel()
        let firstRefreshAt = viewModel.lastRefreshAt
        if case .warning = viewModel.statusTone {} else {
            XCTFail("Expected warning status tone after first refresh")
        }
        XCTAssertFalse(viewModel.refreshWarnings.isEmpty)

        command.logsError = nil
        command.logsResponse = ServiceLogsResponse(ok: true, path: "/tmp/log", lines: ["ok"], errors: nil)
        await viewModel.refreshControlPanel()

        if case .success = viewModel.statusTone {} else {
            XCTFail("Expected success status tone after second refresh")
        }
        XCTAssertTrue(viewModel.refreshWarnings.isEmpty)
        XCTAssertNotNil(viewModel.lastRefreshAt)
        XCTAssertGreaterThanOrEqual(viewModel.lastRefreshAt ?? .distantPast, firstRefreshAt ?? .distantPast)
    }
}

private final class MockCommandService: CommandServiceProtocol {
    let envFilePath = "/tmp/.env"

    var doctorResponse = WizardDoctorResponse(
        ok: true,
        pythonOk: true,
        venvOk: true,
        messagesDbExists: true,
        messagesDbReadable: true,
        connectorBinaryFound: true,
        connectorBinaryPath: "",
        adminApiTokenPresent: true,
        errors: []
    )
    var generateEnvResponse = WizardGenerateEnvResponse(ok: true, envPreview: "", validationErrors: [], errors: nil)
    var ensureGatewaysResponse = WizardEnsureGatewaysResponse(ok: true, results: [], errors: nil)
    var configValidateResponse = ConfigValidateResponse(ok: true, errors: [], warnings: [], code: nil)
    var configWriteResponse = ConfigWriteResponse(ok: true, updatedKeys: [], errors: [], code: nil)
    var configReadResponse = ConfigReadResponse(ok: true, values: [:], errors: nil)
    var serviceStatusResponse = ServiceStatusResponse(ok: true, launchdLoaded: false, launchdPid: nil, daemonProcessDetected: false, plistPath: "", healthy: false, errors: nil)
    var serviceActionResponse = ServiceActionResponse(ok: true, label: nil, plistPath: nil, pythonBin: nil, errors: nil, code: nil)
    var logsResponse = ServiceLogsResponse(ok: true, path: "", lines: [], errors: nil)

    var serviceRestartCallCount = 0
    var serviceStatusCallCount = 0
    var createAgentOfficeScaffoldCallCount = 0
    var serviceStatusError: Error?
    var configReadError: Error?
    var logsError: Error?
    var serviceStatusDelayNanoseconds: UInt64 = 0

    func wizardDoctor() async throws -> WizardDoctorResponse { doctorResponse }
    func wizardGenerateEnv(onboarding: OnboardingState) async throws -> WizardGenerateEnvResponse { generateEnvResponse }
    func wizardEnsureGateways(onboarding: OnboardingState) async throws -> WizardEnsureGatewaysResponse { ensureGatewaysResponse }
    func configValidate() async throws -> ConfigValidateResponse { configValidateResponse }
    func configWrite(setValues: [String]) async throws -> ConfigWriteResponse { configWriteResponse }
    func configRead(keys: [String]) async throws -> ConfigReadResponse {
        if let error = configReadError {
            throw error
        }
        return configReadResponse
    }
    func serviceStatus() async throws -> ServiceStatusResponse {
        serviceStatusCallCount += 1
        if serviceStatusDelayNanoseconds > 0 {
            try? await Task.sleep(nanoseconds: serviceStatusDelayNanoseconds)
        }
        if let error = serviceStatusError {
            throw error
        }
        return serviceStatusResponse
    }
    func serviceInstall() async throws -> ServiceActionResponse { serviceActionResponse }
    func serviceStart() async throws -> ServiceActionResponse { serviceActionResponse }
    func serviceStop() async throws -> ServiceActionResponse { serviceActionResponse }
    func serviceRestart() async throws -> ServiceActionResponse {
        serviceRestartCallCount += 1
        return serviceActionResponse
    }
    func serviceLogs(stream: String, lines: Int) async throws -> ServiceLogsResponse {
        if let error = logsError {
            throw error
        }
        return logsResponse
    }
    func openTerminal(command: String) async throws {}
    func createAgentOfficeScaffold() async throws {
        createAgentOfficeScaffoldCallCount += 1
    }
}

private final class MockAdminClient: AdminApiClientProtocol {
    func health() async throws -> Bool { true }
    func metrics() async throws -> MetricsResponse { MetricsResponse(activeSessions: 1, pendingApprovals: 0, recentEvents: 0) }
    func sessions() async throws -> [SessionItem] { [] }
    func approvals() async throws -> [ApprovalItem] { [] }
    func overrideApproval(requestID: String, status: String) async throws -> ApprovalOverrideResponse {
        ApprovalOverrideResponse(requestId: requestID, status: status)
    }
    func events(limit: Int) async throws -> [AuditEvent] { [] }
}
