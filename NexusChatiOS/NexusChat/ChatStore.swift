import Foundation

@MainActor
final class ChatStore: ObservableObject {
    @Published var conversations: [Conversation] = []
    @Published var selectedConversationID: UUID?
    @Published var draft = ""
    @Published var isSending = false
    @Published var errorMessage: String?
    @Published var status: ConnectionStatus = .checking
    @Published var apiBaseURL = UserDefaults.standard.string(forKey: Keys.apiBaseURL) ?? "http://127.0.0.1:8000/api" {
        didSet { UserDefaults.standard.set(apiBaseURL, forKey: Keys.apiBaseURL) }
    }
    @Published var authToken = UserDefaults.standard.string(forKey: Keys.authToken) ?? "" {
        didSet { UserDefaults.standard.set(authToken, forKey: Keys.authToken) }
    }
    @Published var appearance = AppAppearance(rawValue: UserDefaults.standard.string(forKey: Keys.appearance) ?? "") ?? .system {
        didSet { UserDefaults.standard.set(appearance.rawValue, forKey: Keys.appearance) }
    }

    private enum Keys {
        static let conversations = "nexus.conversations"
        static let apiBaseURL = "nexus.apiBaseURL"
        static let authToken = "nexus.authToken"
        static let appearance = "nexus.appearance"
    }

    init() {
        loadConversations()
        if conversations.isEmpty {
            createConversation()
        } else {
            selectedConversationID = conversations.sorted { $0.updatedAt > $1.updatedAt }.first?.id
        }
        Task { await checkHealth() }
    }

    var selectedConversation: Conversation? {
        guard let selectedConversationID else { return nil }
        return conversations.first { $0.id == selectedConversationID }
    }

    var selectedMessages: [ChatMessage] {
        selectedConversation?.messages ?? []
    }

    func createConversation() {
        let conversation = Conversation(title: "New chat")
        conversations.insert(conversation, at: 0)
        selectedConversationID = conversation.id
        draft = ""
        errorMessage = nil
        saveConversations()
    }

    func deleteConversation(_ conversation: Conversation) {
        conversations.removeAll { $0.id == conversation.id }
        if conversations.isEmpty {
            createConversation()
        } else if selectedConversationID == conversation.id {
            selectedConversationID = conversations.first?.id
        }
        saveConversations()
    }

    func sendDraft() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }
        guard URL(string: apiBaseURL) != nil else {
            errorMessage = NexusAPIError.invalidURL.localizedDescription
            return
        }

        if selectedConversationID == nil {
            createConversation()
        }

        draft = ""
        errorMessage = nil
        isSending = true
        append(ChatMessage(role: .user, content: text))

        do {
            let reply = try await client().send(message: text)
            append(ChatMessage(role: .assistant, content: reply.isEmpty ? "Nexus returned an empty response." : reply))
            status = .online
        } catch {
            errorMessage = error.localizedDescription
            status = .offline
        }

        isSending = false
    }

    func checkHealth() async {
        guard URL(string: apiBaseURL) != nil else {
            status = .offline
            return
        }

        status = .checking
        do {
            try await client().health()
            status = .online
        } catch {
            status = .offline
        }
    }

    func clearSelectedConversation() {
        guard let selectedConversationID,
              let index = conversations.firstIndex(where: { $0.id == selectedConversationID }) else {
            return
        }
        conversations[index].messages.removeAll()
        conversations[index].title = "New chat"
        conversations[index].updatedAt = Date()
        saveConversations()
    }

    private func client() throws -> NexusAPIClient {
        guard let url = URL(string: apiBaseURL) else {
            throw NexusAPIError.invalidURL
        }
        return NexusAPIClient(baseURL: url, token: authToken)
    }

    private func append(_ message: ChatMessage) {
        guard let selectedConversationID,
              let index = conversations.firstIndex(where: { $0.id == selectedConversationID }) else {
            return
        }

        conversations[index].messages.append(message)
        conversations[index].updatedAt = Date()
        if message.role == .user, conversations[index].title == "New chat" {
            conversations[index].title = title(from: message.content)
        }
        conversations.sort { $0.updatedAt > $1.updatedAt }
        saveConversations()
    }

    private func title(from text: String) -> String {
        let compact = text.replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if compact.count <= 36 { return compact }
        return String(compact.prefix(36)).trimmingCharacters(in: .whitespacesAndNewlines) + "..."
    }

    private func loadConversations() {
        guard let data = UserDefaults.standard.data(forKey: Keys.conversations),
              let decoded = try? JSONDecoder().decode([Conversation].self, from: data) else {
            conversations = []
            return
        }
        conversations = decoded.sorted { $0.updatedAt > $1.updatedAt }
    }

    private func saveConversations() {
        guard let data = try? JSONEncoder().encode(conversations) else { return }
        UserDefaults.standard.set(data, forKey: Keys.conversations)
    }
}
