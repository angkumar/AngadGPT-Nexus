import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var store: ChatStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    TextField("API base URL", text: $store.apiBaseURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()

                    SecureField("Auth token", text: $store.authToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    HStack {
                        StatusPill(status: store.status)
                        Spacer()
                        Button("Check") {
                            Task { await store.checkHealth() }
                        }
                    }
                }

                Section("Appearance") {
                    Picker("Theme", selection: $store.appearance) {
                        ForEach(AppAppearance.allCases) { appearance in
                            Text(appearance.title).tag(appearance)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Current chat") {
                    Button(role: .destructive) {
                        store.clearSelectedConversation()
                    } label: {
                        Label("Clear messages", systemImage: "trash")
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
