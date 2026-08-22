import SwiftUI

@main
struct BankrApp: App {
    @StateObject private var session = SessionStore(sessionToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzMzFlZmUxZi1jN2YwLTQwZWQtYjFlYy0zOTg0NjEzZDcwYWMiLCJleHAiOjE3ODk1MjUzNjh9.TWQ5zwb8dxI54Wm8oml3re9W1KVH__-Min-WC1XbXYU")

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
        }
    }
}
