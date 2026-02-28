import Foundation

protocol CommandServiceProtocol {
    var envFilePath: String { get }

    func wizardDoctor() async throws -> WizardDoctorResponse
    func wizardGenerateEnv(onboarding: OnboardingState) async throws -> WizardGenerateEnvResponse
    func wizardEnsureGateways(onboarding: OnboardingState) async throws -> WizardEnsureGatewaysResponse

    func configValidate() async throws -> ConfigValidateResponse
    func configWrite(setValues: [String]) async throws -> ConfigWriteResponse
    func configRead(keys: [String]) async throws -> ConfigReadResponse

    func serviceStatus() async throws -> ServiceStatusResponse
    func serviceInstall() async throws -> ServiceActionResponse
    func serviceStart() async throws -> ServiceActionResponse
    func serviceStop() async throws -> ServiceActionResponse
    func serviceRestart() async throws -> ServiceActionResponse
    func serviceLogs(stream: String, lines: Int) async throws -> ServiceLogsResponse

    func openTerminal(command: String) async throws
    func createAgentOfficeScaffold() async throws
}

final class CommandService: CommandServiceProtocol {
    private let repositoryRoot: URL
    private let pythonExecutable: URL
    private let decoder: JSONDecoder

    init(repositoryRoot: URL? = nil) {
        let detectedRoot = repositoryRoot ?? Self.detectRepositoryRoot()
        self.repositoryRoot = detectedRoot
        let venvPython = detectedRoot.appendingPathComponent(".venv/bin/python")
        if FileManager.default.fileExists(atPath: venvPython.path) {
            self.pythonExecutable = venvPython
        } else {
            self.pythonExecutable = URL(fileURLWithPath: "/usr/bin/env")
        }

        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    var envFilePath: String {
        repositoryRoot.appendingPathComponent(".env").path
    }

    func wizardDoctor() async throws -> WizardDoctorResponse {
        try await runJSON(arguments: ["wizard", "doctor", "--json"], as: WizardDoctorResponse.self)
    }

    func wizardGenerateEnv(onboarding: OnboardingState) async throws -> WizardGenerateEnvResponse {
        let gateways = gatewaysString(onboarding)
        var args = [
            "wizard",
            "generate-env",
            "--json",
            "--phone", onboarding.phone,
            "--connector", onboarding.connector,
            "--connector-command", onboarding.connectorCommand,
            "--workspace", onboarding.workspace,
            "--gateways", gateways,
            "--reminders-list-name", onboarding.remindersListName,
            "--reminders-archive-list-name", onboarding.remindersArchiveListName,
            "--notes-folder-name", onboarding.notesFolderName,
            "--notes-archive-folder-name", onboarding.notesArchiveFolderName,
            "--notes-log-folder-name", onboarding.notesLogFolderName,
            "--calendar-name", onboarding.calendarName,
            "--soul-file", onboarding.soulFile,
        ]
        if onboarding.enableAgentOffice {
            args.append("--enable-agent-office")
        }
        if onboarding.enableNotesLogging {
            args.append("--enable-notes-logging")
        }
        if onboarding.enableMail {
            args += ["--mail-address", onboarding.mailAddress]
        }
        return try await runJSON(arguments: args, as: WizardGenerateEnvResponse.self)
    }

    func wizardEnsureGateways(onboarding: OnboardingState) async throws -> WizardEnsureGatewaysResponse {
        var args = ["wizard", "ensure-gateways", "--json"]
        if onboarding.enableReminders {
            args.append("--enable-reminders")
        }
        if onboarding.enableNotes {
            args.append("--enable-notes")
        }
        if onboarding.enableNotesLogging {
            args.append("--enable-notes-logging")
        }
        if onboarding.enableCalendar {
            args.append("--enable-calendar")
        }
        args += ["--reminders-list-name", onboarding.remindersListName]
        args += ["--reminders-archive-list-name", onboarding.remindersArchiveListName]
        args += ["--notes-folder-name", onboarding.notesFolderName]
        args += ["--notes-archive-folder-name", onboarding.notesArchiveFolderName]
        args += ["--notes-log-folder-name", onboarding.notesLogFolderName]
        args += ["--calendar-name", onboarding.calendarName]
        return try await runJSON(arguments: args, as: WizardEnsureGatewaysResponse.self)
    }

    func configValidate() async throws -> ConfigValidateResponse {
        try await runJSON(arguments: ["config", "validate", "--json"], as: ConfigValidateResponse.self)
    }

    func configWrite(setValues: [String]) async throws -> ConfigWriteResponse {
        var args = ["config", "write", "--json"]
        for value in setValues {
            args += ["--set", value]
        }
        return try await runJSON(arguments: args, as: ConfigWriteResponse.self)
    }

    func configRead(keys: [String]) async throws -> ConfigReadResponse {
        var args = ["config", "read", "--json"]
        for key in keys {
            args += ["--key", key]
        }
        return try await runJSON(arguments: args, as: ConfigReadResponse.self)
    }

    func serviceStatus() async throws -> ServiceStatusResponse {
        try await runJSON(arguments: ["service", "status", "--json"], as: ServiceStatusResponse.self)
    }

    func serviceInstall() async throws -> ServiceActionResponse {
        try await runJSON(arguments: ["service", "install", "--json"], as: ServiceActionResponse.self)
    }

    func serviceStart() async throws -> ServiceActionResponse {
        try await runJSON(arguments: ["service", "start", "--json"], as: ServiceActionResponse.self)
    }

    func serviceStop() async throws -> ServiceActionResponse {
        try await runJSON(arguments: ["service", "stop", "--json"], as: ServiceActionResponse.self)
    }

    func serviceRestart() async throws -> ServiceActionResponse {
        try await runJSON(arguments: ["service", "restart", "--json"], as: ServiceActionResponse.self)
    }

    func serviceLogs(stream: String, lines: Int) async throws -> ServiceLogsResponse {
        try await runJSON(
            arguments: ["service", "logs", "--json", "--stream", stream, "--lines", "\(lines)"],
            as: ServiceLogsResponse.self
        )
    }

    func openTerminal(command: String) async throws {
        let escaped = command
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        let script = "tell application \"Terminal\" to do script \"\(escaped)\""
        _ = try await runRawProcess(
            executable: URL(fileURLWithPath: "/usr/bin/osascript"),
            arguments: ["-e", script],
            includePythonEnv: false
        )
    }

    func createAgentOfficeScaffold() async throws {
        let officeDir = repositoryRoot.appendingPathComponent("agent-office")
        let scriptPath = officeDir.appendingPathComponent("setup.sh")

        guard FileManager.default.fileExists(atPath: scriptPath.path) else {
            throw AppViewError.commandFailed("Agent Office setup script not found at \(scriptPath.path)")
        }

        let result = try await runRawProcess(
            executable: URL(fileURLWithPath: "/bin/bash"),
            arguments: [scriptPath.path],
            currentDirectory: officeDir,
            includePythonEnv: false
        )

        if result.status != 0 {
            let raw = String(data: result.stderrData.isEmpty ? result.stdoutData : result.stderrData, encoding: .utf8) ?? "<no output>"
            throw AppViewError.commandFailed("Failed to scaffold agent-office:\n\(raw)")
        }
    }

    private func gatewaysString(_ onboarding: OnboardingState) -> String {
        var gateways: [String] = []
        if onboarding.enableMail {
            gateways.append("mail")
        }
        if onboarding.enableReminders {
            gateways.append("reminders")
        }
        if onboarding.enableNotes {
            gateways.append("notes")
        }
        if onboarding.enableCalendar {
            gateways.append("calendar")
        }
        return gateways.joined(separator: ",")
    }

    private func runJSON<T: Decodable>(arguments: [String], as type: T.Type) async throws -> T {
        let executable = pythonExecutable
        var processArguments = arguments

        if executable.path == "/usr/bin/env" {
            processArguments = ["python3", "-m", "apple_flow"] + arguments
        } else {
            processArguments = ["-m", "apple_flow"] + arguments
        }

        let result = try await runRawProcess(
            executable: executable,
            arguments: processArguments,
            includePythonEnv: true
        )

        let data = result.stdoutData.isEmpty ? result.stderrData : result.stdoutData
        if data.isEmpty {
            throw AppViewError.commandFailed(
                "Command produced no output: \(result.arguments.joined(separator: " "))"
            )
        }

        do {
            return try decoder.decode(type, from: data)
        } catch {
            if result.status != 0 {
                let raw = String(data: result.stderrData.isEmpty ? result.stdoutData : result.stderrData, encoding: .utf8)
                    ?? "<no stderr>"
                throw AppViewError.commandFailed(
                    "Command failed (\(result.status)): \(result.arguments.joined(separator: " "))\n\(raw)"
                )
            }
            let raw = String(data: data, encoding: .utf8) ?? "<non-utf8 output>"
            throw AppViewError.decodeFailed("Failed to decode JSON: \(raw)")
        }
    }

    private func runRawProcess(
        executable: URL,
        arguments: [String],
        currentDirectory: URL? = nil,
        includePythonEnv: Bool
    ) async throws -> (stdoutData: Data, stderrData: Data, status: Int32, arguments: [String]) {
        try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = executable
            process.arguments = arguments
            process.currentDirectoryURL = currentDirectory ?? repositoryRoot

            var env = ProcessInfo.processInfo.environment
            if includePythonEnv {
                env["PYTHONPATH"] = repositoryRoot.appendingPathComponent("src").path
            }
            process.environment = env

            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe

            process.terminationHandler = { proc in
                let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
                let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                continuation.resume(
                    returning: (
                        stdoutData: stdoutData,
                        stderrData: stderrData,
                        status: proc.terminationStatus,
                        arguments: arguments
                    )
                )
            }

            do {
                try process.run()
            } catch {
                continuation.resume(throwing: error)
            }
        }
    }

    private static func detectRepositoryRoot() -> URL {
        let fm = FileManager.default

        if let explicit = ProcessInfo.processInfo.environment["APPLE_FLOW_REPO_ROOT"], !explicit.isEmpty {
            let url = URL(fileURLWithPath: explicit)
            if isAppleFlowRoot(url, fileManager: fm) {
                return url
            }
        }

        let cwd = URL(fileURLWithPath: fm.currentDirectoryPath)
        if let found = findRoot(start: cwd, fileManager: fm) {
            return found
        }

        let bundleBase = Bundle.main.bundleURL.deletingLastPathComponent()
        if let found = findRoot(start: bundleBase, fileManager: fm) {
            return found
        }

        return cwd
    }

    private static func findRoot(start: URL, fileManager: FileManager) -> URL? {
        var cursor = start
        for _ in 0..<12 {
            if isAppleFlowRoot(cursor, fileManager: fileManager) {
                return cursor
            }
            let parent = cursor.deletingLastPathComponent()
            if parent.path == cursor.path {
                break
            }
            cursor = parent
        }
        return nil
    }

    private static func isAppleFlowRoot(_ url: URL, fileManager: FileManager) -> Bool {
        let pyproject = url.appendingPathComponent("pyproject.toml")
        let module = url.appendingPathComponent("src/apple_flow/__main__.py")
        return fileManager.fileExists(atPath: pyproject.path) && fileManager.fileExists(atPath: module.path)
    }
}
