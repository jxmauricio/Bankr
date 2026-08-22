import Foundation

/// Holds the backend session token in memory for the app's lifetime.
/// TODO: move to Keychain before this touches real accounts -- UserDefaults/
/// in-memory is fine for the sandbox-only MVP milestone, not for production.
@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var sessionToken: String?

    init(sessionToken: String? = nil) {
        self.sessionToken = sessionToken
    }

    var isAuthenticated: Bool { sessionToken != nil }

    func signIn(withIdentityToken identityToken: String) async throws {
        let response = try await BankrAPIClient.shared.signInWithApple(identityToken: identityToken)
        sessionToken = response.sessionToken
    }

    func signOut() {
        sessionToken = nil
    }
}
