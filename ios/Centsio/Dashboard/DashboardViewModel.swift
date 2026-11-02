import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published private(set) var netWorth: CentsioAPIClient.NetWorthHistory?
    @Published private(set) var rollup: CentsioAPIClient.PeriodRollup?
    @Published private(set) var spending: CentsioAPIClient.ItemizedTransactions?
    @Published private(set) var income: CentsioAPIClient.ItemizedTransactions?
    @Published private(set) var goalProgress: CentsioAPIClient.GoalProgress?
    @Published private(set) var isLoading = false
    @Published private(set) var loadFailed = false

    func load(sessionToken: String) async {
        isLoading = true
        loadFailed = false
        defer { isLoading = false }

        do {
            async let netWorth = CentsioAPIClient.shared.fetchNetWorth(sessionToken: sessionToken)
            async let rollup = CentsioAPIClient.shared.fetchRollup(sessionToken: sessionToken)
            async let spending = CentsioAPIClient.shared.fetchSpending(sessionToken: sessionToken)
            async let income = CentsioAPIClient.shared.fetchIncome(sessionToken: sessionToken)
            async let goalProgress = CentsioAPIClient.shared.fetchGoalProgress(sessionToken: sessionToken)

            (self.netWorth, self.rollup, self.spending, self.income, self.goalProgress) =
                try await (netWorth, rollup, spending, income, goalProgress)
        } catch {
            loadFailed = true
        }
    }
}
