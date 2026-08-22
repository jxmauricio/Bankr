import Foundation

enum BankrAPIError: Error {
    case invalidResponse
    case server(statusCode: Int)
}

/// Thin wrapper around the Bankr backend. The app never talks to Plaid or
/// Claude directly -- every call goes through here so secrets stay
/// server-side (see backend/README.md).
struct BankrAPIClient {
    static let shared = BankrAPIClient()

    /// Points at a local `uvicorn app.main:app --reload` by default.
    /// Swap for a staging/production URL via build configuration once one exists.
    var baseURL = URL(string: "http://localhost:8000")!

    private var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .formatted(Self.dateOnlyFormatter)
        return encoder
    }

    private static let dateOnlyFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    private func request(
        path: String,
        method: String,
        sessionToken: String? = nil,
        body: (any Encodable)? = nil,
        queryItems: [URLQueryItem] = []
    ) async throws -> Data {
        var url = baseURL.appendingPathComponent(path)
        if !queryItems.isEmpty {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            components.queryItems = queryItems
            url = components.url!
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        if let sessionToken {
            request.setValue("Bearer \(sessionToken)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(body)
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw BankrAPIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else { throw BankrAPIError.server(statusCode: http.statusCode) }
        return data
    }

    // MARK: - Auth

    struct SessionResponse: Decodable {
        let sessionToken: String
    }

    func signInWithApple(identityToken: String) async throws -> SessionResponse {
        struct Body: Encodable { let identityToken: String }
        let data = try await request(
            path: "auth/apple", method: "POST", body: Body(identityToken: identityToken)
        )
        return try decoder.decode(SessionResponse.self, from: data)
    }

    // MARK: - Goals

    struct GoalResponse: Decodable {
        let id: String
        let type: String
        let targetAmount: Double
        let targetDate: String?
        let startingAmount: Double
        let currentProgressAmount: Double
        let status: String
    }

    struct GoalProgress: Decodable {
        let type: String?
        let targetAmount: Double?
        let currentProgressAmount: Double?
        let progressFraction: Double?
        let targetDate: String?
        let expectedProgressFraction: Double?
        let onPace: Bool?

        var hasActiveGoal: Bool { type != nil }
    }

    func createGoal(
        type: String, targetAmount: Double, targetDate: Date?, sessionToken: String
    ) async throws -> GoalResponse {
        struct Body: Encodable {
            let type: String
            let targetAmount: Double
            let targetDate: Date?
        }
        let data = try await request(
            path: "goals",
            method: "POST",
            sessionToken: sessionToken,
            body: Body(type: type, targetAmount: targetAmount, targetDate: targetDate)
        )
        return try decoder.decode(GoalResponse.self, from: data)
    }

    func fetchGoalProgress(sessionToken: String) async throws -> GoalProgress {
        let data = try await request(path: "dashboard/goal-progress", method: "GET", sessionToken: sessionToken)
        return try decoder.decode(GoalProgress.self, from: data)
    }

    // MARK: - Dashboard

    struct NetWorthHistory: Decodable {
        struct Point: Decodable {
            let date: String
            let netWorth: Double
        }
        let current: Double?
        let history: [Point]
    }

    struct PeriodRollup: Decodable {
        let period: String
        let income: Double
        let spending: Double
        let gain: Double
    }

    struct ItemizedTransactions: Decodable {
        struct Item: Decodable {
            let date: String
            let amount: Double
            let merchantName: String?
            let category: String?
            let isPending: Bool
        }
        let period: String
        let total: Double
        let items: [Item]
    }

    func fetchNetWorth(sessionToken: String) async throws -> NetWorthHistory {
        let data = try await request(path: "dashboard/net-worth", method: "GET", sessionToken: sessionToken)
        return try decoder.decode(NetWorthHistory.self, from: data)
    }

    func fetchRollup(period: String = "month", sessionToken: String) async throws -> PeriodRollup {
        let data = try await request(
            path: "dashboard/rollup", method: "GET", sessionToken: sessionToken,
            queryItems: [URLQueryItem(name: "period", value: period)]
        )
        return try decoder.decode(PeriodRollup.self, from: data)
    }

    func fetchSpending(period: String = "month", sessionToken: String) async throws -> ItemizedTransactions {
        let data = try await request(
            path: "dashboard/spending", method: "GET", sessionToken: sessionToken,
            queryItems: [URLQueryItem(name: "period", value: period)]
        )
        return try decoder.decode(ItemizedTransactions.self, from: data)
    }

    func fetchIncome(period: String = "month", sessionToken: String) async throws -> ItemizedTransactions {
        let data = try await request(
            path: "dashboard/income", method: "GET", sessionToken: sessionToken,
            queryItems: [URLQueryItem(name: "period", value: period)]
        )
        return try decoder.decode(ItemizedTransactions.self, from: data)
    }

    // MARK: - Linked Accounts

    struct LinkTokenResponse: Decodable {
        let linkToken: String
    }

    struct LinkAccountResponse: Decodable {
        let linkedAccountCount: Int
        let transactionsSynced: Int
        let netWorth: Double
    }

    func fetchLinkToken(sessionToken: String) async throws -> LinkTokenResponse {
        let data = try await request(path: "linked-accounts/link-token", method: "POST", sessionToken: sessionToken)
        return try decoder.decode(LinkTokenResponse.self, from: data)
    }

    func linkAccount(publicToken: String, sessionToken: String) async throws -> LinkAccountResponse {
        struct Body: Encodable { let publicToken: String }
        let data = try await request(
            path: "linked-accounts",
            method: "POST",
            sessionToken: sessionToken,
            body: Body(publicToken: publicToken)
        )
        return try decoder.decode(LinkAccountResponse.self, from: data)
    }

    // MARK: - Chat

    struct ChatResponse: Decodable {
        let conversationId: String
        let reply: String
    }

    func sendChatMessage(
        _ message: String, conversationId: String?, sessionToken: String
    ) async throws -> ChatResponse {
        struct Body: Encodable {
            let message: String
            let conversationId: String?
        }
        let data = try await request(
            path: "chat",
            method: "POST",
            sessionToken: sessionToken,
            body: Body(message: message, conversationId: conversationId)
        )
        return try decoder.decode(ChatResponse.self, from: data)
    }
}
