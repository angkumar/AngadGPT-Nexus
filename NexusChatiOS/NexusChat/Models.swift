import Foundation
import SwiftUI

enum MessageRole: String, Codable {
    case user
    case assistant
    case system
}

struct ChatMessage: Identifiable, Codable, Equatable {
    var id = UUID()
    var role: MessageRole
    var content: String
    var createdAt = Date()
}

struct Conversation: Identifiable, Codable, Equatable {
    var id = UUID()
    var title: String
    var createdAt = Date()
    var updatedAt = Date()
    var messages: [ChatMessage] = []

    var preview: String {
        messages.last?.content.replacingOccurrences(of: "\n", with: " ") ?? "New chat"
    }
}

enum ConnectionStatus: Equatable {
    case checking
    case online
    case offline

    var label: String {
        switch self {
        case .checking: "Checking"
        case .online: "Online"
        case .offline: "Offline"
        }
    }

    var color: Color {
        switch self {
        case .checking: .secondary
        case .online: .green
        case .offline: .red
        }
    }
}

enum AppAppearance: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: String { rawValue }

    var title: String {
        switch self {
        case .system: "System"
        case .light: "Light"
        case .dark: "Dark"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }
}

struct AgentStepRequest: Encodable {
    let message: String
}

struct AgentStepResponse: Decodable {
    let type: String?
    let tool: String?
    let content: String?
    let action: String?
}

struct WrappedAssistantResponse: Decodable {
    let action: String?
    let content: String?
}
