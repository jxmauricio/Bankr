import XCTest
@testable import Bankr

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
