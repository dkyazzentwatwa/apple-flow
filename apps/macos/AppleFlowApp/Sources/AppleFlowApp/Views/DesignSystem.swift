import SwiftUI
import AppKit

enum AppTheme {
    static let pagePadding: CGFloat = 20
    static let cardSpacing: CGFloat = 14
    static let fieldSpacing: CGFloat = 10
    static let cardCornerRadius: CGFloat = 14

    static let background = Color(nsColor: .windowBackgroundColor)
    static let cardBackground = Color(nsColor: NSColor.controlBackgroundColor).opacity(0.35)
    static let cardStroke = Color.white.opacity(0.08)
    static let subtleText = Color.secondary
    static let success = Color.green
    static let warning = Color.orange
    static let error = Color.red
    static let info = Color.blue
}

struct SectionCard<Content: View>: View {
    let title: String
    let subtitle: String?
    @ViewBuilder let content: Content

    init(_ title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(title)
                    .font(.headline)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(AppTheme.subtleText)
                }
                Spacer()
            }
            content
        }
        .padding(14)
        .background(AppTheme.cardBackground)
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.cardCornerRadius)
                .stroke(AppTheme.cardStroke, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.cardCornerRadius))
    }
}

struct StatusChip: View {
    let text: String
    let tone: StatusTone

    private var toneColor: Color {
        switch tone {
        case .success: return AppTheme.success
        case .warning: return AppTheme.warning
        case .error: return AppTheme.error
        case .loading: return AppTheme.info
        case .info: return AppTheme.info
        }
    }

    private var iconName: String {
        switch tone {
        case .success: return "checkmark.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        case .error: return "xmark.octagon.fill"
        case .loading: return "clock.arrow.circlepath"
        case .info: return "info.circle.fill"
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: iconName)
            Text(text)
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .foregroundStyle(toneColor)
        .background(toneColor.opacity(0.14))
        .clipShape(Capsule())
    }
}

struct FieldHelpPopover: View {
    let descriptor: ConfigFieldDescriptor

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(descriptor.label)
                .font(.headline)
            Text(descriptor.description)
                .font(.callout)
            if !descriptor.validationHint.isEmpty {
                Text(descriptor.validationHint)
                    .font(.caption)
                    .foregroundStyle(AppTheme.subtleText)
            }
            if !descriptor.example.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Example")
                        .font(.caption.weight(.semibold))
                    Text(descriptor.example)
                        .font(.system(.caption, design: .monospaced))
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.white.opacity(0.06))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
            }
            if descriptor.required {
                StatusChip(text: "Required", tone: .warning)
            }
        }
        .padding(12)
        .frame(width: 320, alignment: .leading)
    }
}

struct InlineHelpBadge: View {
    let descriptor: ConfigFieldDescriptor
    @State private var showPopover = false

    var body: some View {
        Button {
            showPopover.toggle()
        } label: {
            Image(systemName: "questionmark.circle")
                .foregroundStyle(AppTheme.info)
        }
        .buttonStyle(.plain)
        .help(descriptor.description)
        .popover(isPresented: $showPopover, arrowEdge: .bottom) {
            FieldHelpPopover(descriptor: descriptor)
        }
    }
}

struct FieldValidationBadge: View {
    let state: FieldValidationState

    var body: some View {
        switch state {
        case .neutral:
            EmptyView()
        case .valid:
            StatusChip(text: "Valid", tone: .success)
        case .warning(let message):
            StatusChip(text: message, tone: .warning)
        case .error(let message):
            StatusChip(text: message, tone: .error)
        }
    }
}
