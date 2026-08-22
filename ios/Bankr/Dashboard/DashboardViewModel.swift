import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published private(set) var netWorth: BankrAPIClient.NetWorthHistory?
    @Published private(set) var rollup: BankrAPIClient.PeriodRollup?
    @Published private(set) var spending: BankrAPIClient.ItemizedTransactions?
    @Published private(set) var income: BankrAPIClient.ItemizedTransactions?
    @Published private(set) var goalProgress: BankrAPIClient.GoalProgress?
    @Published private(set) var isLoading = false
    @Published private(set) var loadFailed = false

    func load(sessionToken: String) async {
        isLoading = true
        loadFailed = false
        defer { isLoading = false }

        do {
            async let netWorth = BankrAPIClient.shared.fetchNetWorth(sessionToken: sessionToken)
            async let rollup = BankrAPIClient.shared.fetchRollup(sessionToken: sessionToken)
            async let spending = BankrAPIClient.shared.fetchSpending(sessionToken: sessionToken)
            async let income = BankrAPIClient.shared.fetchIncome(sessionToken: sessionToken)
            async let goalProgress = BankrAPIClient.shared.fetchGoalProgress(sessionToken: sessionToken)

            (self.netWorth, self.rollup, self.spending, self.income, self.goalProgress) =
                try await (netWorth, rollup, spending, income, goalProgress)
        } catch {
            loadFailed = true
        }
    }
}
