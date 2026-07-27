import SwiftUI

struct ChatView: View {
    @EnvironmentObject private var store: ChatStore
    @FocusState private var isComposerFocused: Bool
    @State private var showingSettings = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 0) {
                        if store.selectedMessages.isEmpty {
                            EmptyChatView()
                                .padding(.top, 56)
                        } else {
                            ForEach(store.selectedMessages) { message in
                                MessageRow(message: message)
                                    .id(message.id)
                            }
                        }

                        if store.isSending {
                            AssistantThinkingRow()
                                .id("thinking")
                        }
                    }
                    .padding(.horizontal, 18)
                    .padding(.bottom, 16)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: store.selectedMessages) { _, messages in
                    guard let last = messages.last else { return }
                    withAnimation(.snappy) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
                .onChange(of: store.isSending) { _, isSending in
                    if isSending {
                        withAnimation(.snappy) {
                            proxy.scrollTo("thinking", anchor: .bottom)
                        }
                    }
                }
            }

            if let error = store.errorMessage {
                ErrorBanner(message: error)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 8)
            }

            ComposerView(isFocused: $isComposerFocused)
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .navigationBar)
        .sheet(isPresented: $showingSettings) {
            SettingsView()
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            IconButton(systemName: "square.and.pencil", accessibilityLabel: "New chat") {
                store.createConversation()
            }

            VStack(spacing: 2) {
                Text("Nexus")
                    .font(.headline.weight(.semibold))
                HStack(spacing: 6) {
                    Text("Local agent")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Circle()
                        .fill(store.status.color)
                        .frame(width: 6, height: 6)
                }
            }
            .frame(maxWidth: .infinity)

            IconButton(systemName: "ellipsis", accessibilityLabel: "Settings") {
                showingSettings = true
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.background)
    }
}

private struct EmptyChatView: View {
    var body: some View {
        VStack(spacing: 22) {
            ZStack {
                Circle()
                    .fill(.primary.opacity(0.08))
                    .frame(width: 74, height: 74)
                Text("N")
                    .font(.system(size: 32, weight: .semibold, design: .rounded))
            }

            Text("How can I help?")
                .font(.title2.weight(.semibold))

            VStack(spacing: 10) {
                SuggestionPill(text: "Summarize this repo")
                SuggestionPill(text: "List the tools Nexus can use")
                SuggestionPill(text: "Help me plan the next feature")
            }
        }
        .frame(maxWidth: .infinity)
    }
}

private struct SuggestionPill: View {
    @EnvironmentObject private var store: ChatStore
    let text: String

    var body: some View {
        Button {
            store.draft = text
        } label: {
            Text(text)
                .font(.subheadline)
                .lineLimit(1)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(.regularMaterial, in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

private struct MessageRow: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if message.role == .assistant {
                AvatarView()
            } else {
                Spacer(minLength: 42)
            }

            messageBody

            if message.role == .assistant {
                Spacer(minLength: 28)
            }
        }
        .padding(.vertical, 14)
    }

    private var messageBody: some View {
        Group {
            if message.role == .user {
                Text(message.content)
                    .font(.body)
                    .textSelection(.enabled)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            } else {
                MarkdownText(content: message.content)
                    .font(.body)
                    .lineSpacing(4)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

private struct AssistantThinkingRow: View {
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            AvatarView()
            ThinkingIndicator()
            Spacer()
        }
        .padding(.vertical, 14)
    }
}

private struct AvatarView: View {
    var body: some View {
        ZStack {
            Circle()
                .fill(.primary.opacity(0.08))
            Text("N")
                .font(.caption.weight(.bold))
        }
        .frame(width: 30, height: 30)
    }
}

private struct ErrorBanner: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
            Text(message)
                .font(.caption)
                .lineLimit(4)
            Spacer()
        }
        .foregroundStyle(.red)
        .padding(10)
        .background(.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct ComposerView: View {
    @EnvironmentObject private var store: ChatStore
    var isFocused: FocusState<Bool>.Binding

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Message Nexus", text: $store.draft, axis: .vertical)
                .focused(isFocused)
                .lineLimit(1...6)
                .textFieldStyle(.plain)
                .padding(.horizontal, 14)
                .padding(.vertical, 12)

            Button {
                Task { await store.sendDraft() }
            } label: {
                Image(systemName: store.isSending ? "stop.fill" : "arrow.up")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(sendButtonForeground)
                    .frame(width: 32, height: 32)
                    .background(sendButtonBackground, in: Circle())
            }
            .buttonStyle(.plain)
            .disabled(sendDisabled)
            .padding(.trailing, 8)
            .padding(.bottom, 8)
            .accessibilityLabel("Send message")
        }
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
    }

    private var sendDisabled: Bool {
        store.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.isSending
    }

    private var sendButtonForeground: Color {
        sendDisabled ? .secondary : Color(.systemBackground)
    }

    private var sendButtonBackground: Color {
        sendDisabled ? Color.primary.opacity(0.12) : .primary
    }
}
