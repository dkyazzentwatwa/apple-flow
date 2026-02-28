import Foundation

enum ConfigInputType: String, Decodable {
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

struct ConfigSectionDescriptor: Decodable, Identifiable, Hashable {
    let id: String
    let label: String
    let order: Int
    let defaultExpanded: Bool
}

struct ConfigFieldDescriptor: Decodable, Identifiable, Hashable {
    let key: String
    let name: String
    let label: String
    let sectionId: String
    let description: String
    let required: Bool
    let sensitive: Bool
    let inputType: ConfigInputType
    let defaultValue: String
    let validationHint: String
    let enumOptions: [String]
    let restartRecommended: Bool

    var id: String { key }
    var example: String { defaultValue }
    var placeholder: String { defaultValue }
}

struct ConfigFieldGroup: Identifiable, Hashable {
    let section: ConfigSectionDescriptor
    let fields: [ConfigFieldDescriptor]

    var id: String { section.id }
}
