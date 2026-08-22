import SwiftUI

/// The MVP dashboard: net worth, goal progress, monthly rollup, and itemized
/// spending/income, per the plan's dashboard spec. Replaces the earlier
/// DashboardPlaceholderView now that the backend read endpoints exist.
struct DashboardView: View {
    @EnvironmentObject private var session: SessionStore
    @StateObject private var viewModel = DashboardViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if viewModel.loadFailed {
                    errorView
                } else {
                    netWorthCard
                    goalProgressCard
                    rollupCard
                    itemizedCard(title: "Spending", data: viewModel.spending, tint: .red)
                    itemizedCard(title: "Income", data: viewModel.income, tint: .green)
                }
            }
            .padding()
        }
        .refreshable { await load() }
        .overlay {
            if viewModel.isLoading && viewModel.netWorth == nil {
                ProgressView()
            }
        }
        .task { await load() }
        .navigationTitle("Dashboard")
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                NavigationLink {
                    ChatView()
                } label: {
                    Image(systemName: "bubble.left.and.bubble.right")
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Button("Sign Out", role: .destructive) { session.signOut() }
            }
        }
    }

    private func load() async {
        guard let token = session.sessionToken else { return }
        await viewModel.load(sessionToken: token)
    }

    private var errorView: some View {
        VStack(spacing: 12) {
            Text("Couldn't load your dashboard.").foregroundStyle(.secondary)
            Button("Retry") { Task { await load() } }
        }
        .padding(.top, 80)
    }

    private var netWorthCard: some View {
        card {
            Text("Net Worth").font(.subheadline).foregroundStyle(.secondary)
            Text((viewModel.netWorth?.current ?? 0).asCurrency)
                .font(.system(size: 36, weight: .bold))
        }
    }

    @ViewBuilder
    private var goalProgressCard: some View {
        if let goal = viewModel.goalProgress, goal.hasActiveGoal {
            card {
                Text(goalTitle(goal.type))
                    .font(.subheadline).foregroundStyle(.secondary)
                ProgressView(value: min(max(goal.progressFraction ?? 0, 0), 1))
                    .tint(.accentColor)
                HStack {
                    Text((goal.currentProgressAmount ?? 0).asCurrency)
                        .font(.headline)
                    Text("of \((goal.targetAmount ?? 0).asCurrency)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                    if let onPace = goal.onPace {
                        Label(onPace ? "On pace" : "Behind pace", systemImage: onPace ? "checkmark.circle" : "exclamationmark.triangle")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(onPace ? .green : .orange)
                    }
                }
            }
        }
    }

    private func goalTitle(_ type: String?) -> String {
        switch type {
        case "save_amount": "Savings Goal"
        case "pay_off_debt": "Debt Payoff Goal"
        case "build_emergency_fund": "Emergency Fund Goal"
        default: "Goal"
        }
    }

    private var rollupCard: some View {
        card {
            Text("This Month").font(.subheadline).foregroundStyle(.secondary)
            HStack {
                rollupStat(label: "Income", value: viewModel.rollup?.income ?? 0, color: .green)
                Spacer()
                rollupStat(label: "Spending", value: viewModel.rollup?.spending ?? 0, color: .red)
                Spacer()
                rollupStat(label: "Gain", value: viewModel.rollup?.gain ?? 0, color: .primary)
            }
        }
    }

    private func rollupStat(label: String, value: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value.asCurrency).font(.headline).foregroundStyle(color)
        }
    }

    private func itemizedCard(title: String, data: BankrAPIClient.ItemizedTransactions?, tint: Color) -> some View {
        card {
            HStack {
                Text(title).font(.subheadline).foregroundStyle(.secondary)
                Spacer()
                Text((data?.total ?? 0).asCurrency).font(.subheadline.weight(.semibold))
            }
            if let items = data?.items, !items.isEmpty {
                ForEach(items.prefix(5), id: \.date) { item in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.merchantName ?? item.category ?? "Transaction")
                                .font(.body)
                            if let category = item.category {
                                Text(category).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Text(abs(item.amount).asCurrency)
                            .font(.body.weight(.medium))
                            .foregroundStyle(tint)
                    }
                }
            } else {
                Text("Nothing yet this period.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

#Preview {
    NavigationStack { DashboardView() }
        .environmentObject(SessionStore())
}
