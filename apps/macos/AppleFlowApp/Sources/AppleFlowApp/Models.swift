import Foundation

struct CommandEnvelope: Decodable {
    let ok: Bool
    let code: String?
    let errors: [String]?
}

struct WizardDoctorResponse: Decodable {
    let ok: Bool
    let pythonOk: Bool
    let venvOk: Bool
    let messagesDbExists: Bool
    let messagesDbReadable: Bool
    let connectorBinaryFound: Bool
    let connectorBinaryPath: String
    let adminApiTokenPresent: Bool
    let errors: [String]
}

struct WizardGenerateEnvResponse: Decodable {
    let ok: Bool
    let envPreview: String
    let validationErrors: [String]
    let errors: [String]?
}

struct GatewayResult: Decodable, Identifiable {
    let label: String
    let name: String
    let status: String
    let detail: String

    var id: String { "\(label)-\(name)" }
}

struct WizardEnsureGatewaysResponse: Decodable {
    let ok: Bool
    let results: [GatewayResult]
    let errors: [String]?
}

struct ConfigReadResponse: Decodable {
    let ok: Bool
    let values: [String: String]
    let valueStates: [String: ConfigValueState]?
    let effective: Bool?
    let errors: [String]?

    init(
        ok: Bool,
        values: [String: String],
        valueStates: [String: ConfigValueState]? = nil,
        effective: Bool? = nil,
        errors: [String]? = nil
    ) {
        self.ok = ok
        self.values = values
        self.valueStates = valueStates
        self.effective = effective
        self.errors = errors
    }
}

struct ConfigValueState: Decodable {
    let raw: String
    let effective: String
    let source: String
}

struct ConfigSchemaResponse: Decodable {
    let ok: Bool
    let schemaVersion: String
    let sections: [ConfigSectionDescriptor]
    let fields: [ConfigFieldDescriptor]
    let errors: [String]?
}

struct ConfigValidateResponse: Decodable {
    let ok: Bool
    let errors: [String]
    let warnings: [String]
    let code: String?
}

struct ConfigWriteResponse: Decodable {
    let ok: Bool
    let updatedKeys: [String]
    let errors: [String]
    let code: String?
}

struct ServiceStatusResponse: Decodable {
    let ok: Bool
    let launchdLoaded: Bool
    let launchdPid: Int?
    let daemonProcessDetected: Bool
    let plistPath: String
    let healthy: Bool
    let errors: [String]?
}

struct ServiceActionResponse: Decodable {
    let ok: Bool
    let label: String?
    let plistPath: String?
    let pythonBin: String?
    let errors: [String]?
    let code: String?
}

struct ServiceLogsResponse: Decodable {
    let ok: Bool
    let path: String
    let lines: [String]
    let errors: [String]?
}

struct MetricsResponse: Decodable {
    let activeSessions: Int
    let pendingApprovals: Int
    let recentEvents: Int
}

struct SessionItem: Decodable, Identifiable {
    let sender: String
    let threadId: String?
    let mode: String?
    let lastSeenAt: String?

    var id: String { sender }
}

struct ApprovalItem: Decodable, Identifiable {
    let requestId: String
    let runId: String
    let sender: String
    let summary: String
    let commandPreview: String?
    let createdAt: String?
    let expiresAt: String?
    let status: String

    var id: String { requestId }
}

struct AuditEvent: Decodable, Identifiable {
    let eventId: String
    let runId: String?
    let step: String?
    let eventType: String
    let payloadJson: String?
    let createdAt: String?

    var id: String { eventId }
}

struct ApprovalOverrideResponse: Decodable {
    let requestId: String
    let status: String
}

struct AdminCredentials {
    let host: String
    let port: Int
    let token: String
}

enum AppRoute {
    case intro
    case loading
    case onboarding
    case controlPanel
}

struct OnboardingState {
    var phone: String = ""
    var connector: String = "codex-cli"
    var connectorCommand: String = "codex"
    var workspace: String = ""
    var enableMail: Bool = false
    var mailAddress: String = ""
    var enableReminders: Bool = false
    var enableNotes: Bool = false
    var enableNotesLogging: Bool = false
    var enableCalendar: Bool = false
    var remindersListName: String = "agent-task"
    var remindersArchiveListName: String = "agent-archive"
    var notesFolderName: String = "agent-task"
    var notesArchiveFolderName: String = "agent-archive"
    var notesLogFolderName: String = "agent-logs"
    var calendarName: String = "agent-schedule"
    var enableAgentOffice: Bool = false
    var createAgentOfficeScaffold: Bool = true
    var soulFile: String = "agent-office/SOUL.md"
}

enum AppViewError: Error, LocalizedError {
    case commandFailed(String)
    case decodeFailed(String)
    case networkFailed(String)

    var errorDescription: String? {
        switch self {
        case .commandFailed(let message):
            return message
        case .decodeFailed(let message):
            return message
        case .networkFailed(let message):
            return message
        }
    }
}
