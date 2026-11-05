import SwiftUI

@main
struct CentsioApp: App {
    #if DEBUG
    // Skips Sign in with Apple against a local backend: a session for a user in
    // the local database, signed with the local SESSION_JWT_SECRET. Release
    // builds start signed out, since production rejects this token.
    @StateObject private var session = SessionStore(sessionToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzMzFlZmUxZi1jN2YwLTQwZWQtYjFlYy0zOTg0NjEzZDcwYWMiLCJleHAiOjE3ODk1MjUzNjh9.TWQ5zwb8dxI54Wm8oml3re9W1KVH__-Min-WC1XbXYU")
    #else
    @StateObject private var session = SessionStore()
    #endif

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
        }
    }
}
