import XCTest
@testable import Centsio

@MainActor
final class SessionStoreTests: XCTestCase {
    func testStartsSignedOut() {
        let session = SessionStore()
        XCTAssertFalse(session.isAuthenticated)
    }

    func testSignOutClearsToken() {
        let session = SessionStore()
        session.signOut()
        XCTAssertFalse(session.isAuthenticated)
    }
}
