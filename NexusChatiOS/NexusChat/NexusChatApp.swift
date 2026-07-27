import SwiftUI

@main
struct NexusChatApp: App {
    @StateObject private var store = ChatStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: ChatStore

    var body: some View {
        NavigationSplitView {
            SidebarView()
        } detail: {
            ChatView()
        }
        .tint(.primary)
        .preferredColorScheme(store.appearance.colorScheme)
    }
}
