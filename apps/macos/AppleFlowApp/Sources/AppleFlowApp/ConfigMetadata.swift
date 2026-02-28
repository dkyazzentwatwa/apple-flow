import Foundation

enum ConfigFieldCategory: String, CaseIterable, Identifiable {
    case accessRouting = "Access & Routing"
    case connector = "Connector"
    case admin = "Admin API"
    case gateways = "Apple Gateways"
    case agentOffice = "Agent Office"

    var id: String { rawValue }
}

enum ConfigInputType {
    case text
    case number
    case bool
    case path
    case token
    case csv
}

enum ConfigFilterScope: String, CaseIterable, Identifiable {
    case all = "All"
    case required = "Required"
    case changed = "Changed"
    case errors = "Errors"

    var id: String { rawValue }
}

enum FieldValidationState: Equatable {
    case neutral
    case valid
    case warning(String)
    case error(String)
}

enum StatusTone {
    case info
    case success
    case warning
    case error
    case loading
}

struct ConfigFieldDescriptor: Identifiable {
    let key: String
    let label: String
    let category: ConfigFieldCategory
    let description: String
    let example: String
    let required: Bool
    let inputType: ConfigInputType
    let placeholder: String
    let validationHint: String
    let sensitive: Bool

    var id: String { key }
}

enum ConfigFieldCatalog {
    static let all: [ConfigFieldDescriptor] = [
        ConfigFieldDescriptor(
            key: "apple_flow_allowed_senders",
            label: "Allowed Senders",
            category: .accessRouting,
            description: "Comma-separated phone numbers allowed to trigger Apple Flow.",
            example: "+15551234567,+15557654321",
            required: true,
            inputType: .csv,
            placeholder: "+15551234567",
            validationHint: "Use E.164 format. Comma-separate multiple senders.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_allowed_workspaces",
            label: "Allowed Workspaces",
            category: .accessRouting,
            description: "Comma-separated list of directories the agent can operate in.",
            example: "/Users/you/code,/Users/you/projects",
            required: true,
            inputType: .csv,
            placeholder: "/Users/you/code",
            validationHint: "Absolute paths are recommended.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_default_workspace",
            label: "Default Workspace",
            category: .accessRouting,
            description: "Primary workspace used when commands do not specify @alias.",
            example: "/Users/you/code/my-project",
            required: true,
            inputType: .path,
            placeholder: "/Users/you/code/my-project",
            validationHint: "Must be one of your allowed workspaces.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_connector",
            label: "Connector",
            category: .connector,
            description: "Connector backend used for AI execution.",
            example: "codex-cli",
            required: true,
            inputType: .text,
            placeholder: "codex-cli",
            validationHint: "Supported: codex-cli, claude-cli, cline.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_codex_cli_command",
            label: "Codex CLI Command",
            category: .connector,
            description: "Executable command for Codex CLI connector mode.",
            example: "codex",
            required: false,
            inputType: .text,
            placeholder: "codex",
            validationHint: "Set when connector is codex-cli.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_claude_cli_command",
            label: "Claude CLI Command",
            category: .connector,
            description: "Executable command for Claude CLI connector mode.",
            example: "claude",
            required: false,
            inputType: .text,
            placeholder: "claude",
            validationHint: "Set when connector is claude-cli.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_cline_command",
            label: "Cline Command",
            category: .connector,
            description: "Executable command for Cline connector mode.",
            example: "cline",
            required: false,
            inputType: .text,
            placeholder: "cline",
            validationHint: "Set when connector is cline.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_admin_host",
            label: "Admin Host",
            category: .admin,
            description: "Host used by the control panel to reach Apple Flow Admin API.",
            example: "127.0.0.1",
            required: true,
            inputType: .text,
            placeholder: "127.0.0.1",
            validationHint: "Usually localhost (127.0.0.1).",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_admin_port",
            label: "Admin Port",
            category: .admin,
            description: "Port for Apple Flow Admin API.",
            example: "8787",
            required: true,
            inputType: .number,
            placeholder: "8787",
            validationHint: "Must be a valid integer port.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_admin_api_token",
            label: "Admin API Token",
            category: .admin,
            description: "Bearer token required by control actions and admin API routes.",
            example: "a1b2c3...32+ chars",
            required: true,
            inputType: .token,
            placeholder: "generated token",
            validationHint: "Keep secret. Required for Control Panel runtime actions.",
            sensitive: true
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_reminders_list_name",
            label: "Reminders Task List",
            category: .gateways,
            description: "Reminders list watched for active tasks.",
            example: "agent-task",
            required: false,
            inputType: .text,
            placeholder: "agent-task",
            validationHint: "Used when reminders polling is enabled.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_reminders_archive_list_name",
            label: "Reminders Archive List",
            category: .gateways,
            description: "Reminders list used for completed or archived items.",
            example: "agent-archive",
            required: false,
            inputType: .text,
            placeholder: "agent-archive",
            validationHint: "Used when reminders polling is enabled.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_notes_folder_name",
            label: "Notes Task Folder",
            category: .gateways,
            description: "Apple Notes folder watched for inbound notes tasks.",
            example: "agent-task",
            required: false,
            inputType: .text,
            placeholder: "agent-task",
            validationHint: "Used when notes polling is enabled.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_notes_archive_folder_name",
            label: "Notes Archive Folder",
            category: .gateways,
            description: "Archive folder for completed note-based tasks.",
            example: "agent-archive",
            required: false,
            inputType: .text,
            placeholder: "agent-archive",
            validationHint: "Used when notes polling is enabled.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_notes_log_folder_name",
            label: "Notes Log Folder",
            category: .gateways,
            description: "Folder used when Notes logging is enabled.",
            example: "agent-logs",
            required: false,
            inputType: .text,
            placeholder: "agent-logs",
            validationHint: "Used when notes logging is enabled.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_calendar_name",
            label: "Calendar Name",
            category: .gateways,
            description: "Calendar watched for due events and task routing.",
            example: "agent-schedule",
            required: false,
            inputType: .text,
            placeholder: "agent-schedule",
            validationHint: "Used when calendar polling is enabled.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_enable_memory",
            label: "Enable Agent Office Memory",
            category: .agentOffice,
            description: "Turns on agent-office memory injection and topic memory writes.",
            example: "true",
            required: false,
            inputType: .bool,
            placeholder: "true or false",
            validationHint: "Use true/false only.",
            sensitive: false
        ),
        ConfigFieldDescriptor(
            key: "apple_flow_soul_file",
            label: "SOUL.md Path",
            category: .agentOffice,
            description: "Path to SOUL.md defining companion identity/personality.",
            example: "agent-office/SOUL.md",
            required: false,
            inputType: .path,
            placeholder: "agent-office/SOUL.md",
            validationHint: "Relative to repo root or absolute path.",
            sensitive: false
        ),
    ]

    static let byKey: [String: ConfigFieldDescriptor] = Dictionary(uniqueKeysWithValues: all.map { ($0.key, $0) })
}
