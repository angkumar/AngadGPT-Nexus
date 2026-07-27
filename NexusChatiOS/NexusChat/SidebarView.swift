import SwiftUI

struct SidebarView: View {
    @EnvironmentObject private var store: ChatStore
    @State private var showingSettings = false

    var body: some View {
        List(selection: $store.selectedConversationID) {
            Section {
                Button {
                    store.createConversation()
                } label: {
                    Label("New chat", systemImage: "square.and.pencil")
                }
            }

            Section("Chats") {
                ForEach(store.conversations) { conversation in
                    ConversationRow(conversation: conversation)
                        .tag(conversation.id)
                        .swipeActions {
                            Button(role: .destructive) {
                                store.deleteConversation(conversation)
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            }
        }
        .navigationTitle("Nexus")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                IconButton(systemName: "gearshape", accessibilityLabel: "Settings") {
                    showingSettings = true
                }
            }
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView()
        }
    }
}

private struct ConversationRow: View {
    let conversation: Conversation

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(conversation.title)
                .font(.subheadline.weight(.medium))
                .lineLimit(1)
            Text(conversation.preview)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }
}
