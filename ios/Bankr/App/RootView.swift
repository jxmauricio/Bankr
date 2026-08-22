import SwiftUI

struct RootView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        if session.isAuthenticated {
            PostSignInGateView()
        } else {
            WelcomeView()
        }
    }
}

private enum OnboardingStep {
    case linkBank
    case setGoal
    case dashboard
}

/// Decides where to land post-sign-in: bank linking -> goal setup ->
/// dashboard, per the onboarding flow in the plan. Bank linking comes before
/// goal setup so the first goal can be seeded from a real starting balance
/// instead of $0 (see backend/app/services/goal_service.py create_goal).
private struct PostSignInGateView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var step: OnboardingStep?
    @State private var loadFailed = false

    var body: some View {
        Group {
            switch step {
            case .dashboard:
                NavigationStack { DashboardView() }
            case .setGoal:
                GoalSetupView { step = .dashboard }
            case .linkBank:
                LinkBankAccountView { step = .setGoal }
            case .none:
                if loadFailed {
                    retryView
                } else {
                    ProgressView().task { await loadOnboardingState() }
                }
            }
        }
    }

    private var retryView: some View {
        VStack(spacing: 12) {
            Text("Couldn't reach Bankr.").foregroundStyle(.secondary)
            Button("Retry") {
                loadFailed = false
                Task { await loadOnboardingState() }
            }
        }
    }

    private func loadOnboardingState() async {
        guard let token = session.sessionToken else { return }
        do {
            async let netWorth = BankrAPIClient.shared.fetchNetWorth(sessionToken: token)
            async let goalProgress = BankrAPIClient.shared.fetchGoalProgress(sessionToken: token)
            let (netWorthResult, goalResult) = try await (netWorth, goalProgress)

            if netWorthResult.current == nil {
                step = .linkBank
            } else if !goalResult.hasActiveGoal {
                step = .setGoal
            } else {
                step = .dashboard
            }
        } catch {
            loadFailed = true
        }
    }
}
