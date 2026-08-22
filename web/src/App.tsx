import { useEffect, useState } from "react";
import { fetchGoalProgress, fetchNetWorth } from "./lib/api";
import { useSession } from "./lib/session";
import { AuthPage } from "./pages/AuthPage";
import { LinkBankPage } from "./pages/LinkBankPage";
import { GoalSetupPage } from "./pages/GoalSetupPage";
import { DashboardPage } from "./pages/DashboardPage";

type OnboardingStep = "loading" | "link-bank" | "set-goal" | "dashboard" | "load-failed";

export function App() {
  const { token, isAuthenticated } = useSession();

  if (!isAuthenticated) return <AuthPage />;
  return <PostSignInGate key={token} />;
}

function PostSignInGate() {
  const { token } = useSession();
  const [step, setStep] = useState<OnboardingStep>("loading");

  async function loadOnboardingState() {
    if (!token) return;
    setStep("loading");
    try {
      const [netWorth, goalProgress] = await Promise.all([fetchNetWorth(token), fetchGoalProgress(token)]);
      if (netWorth.current === null) {
        setStep("link-bank");
      } else if (!goalProgress.type) {
        setStep("set-goal");
      } else {
        setStep("dashboard");
      }
    } catch {
      setStep("load-failed");
    }
  }

  useEffect(() => {
    loadOnboardingState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  switch (step) {
    case "dashboard":
      return <DashboardPage />;
    case "set-goal":
      return <GoalSetupPage onGoalSet={() => setStep("dashboard")} />;
    case "link-bank":
      return <LinkBankPage onLinked={() => setStep("set-goal")} />;
    case "load-failed":
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
          <p className="text-ink-soft">Couldn't reach Bankr.</p>
          <button
            type="button"
            onClick={loadOnboardingState}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-strong cursor-pointer"
          >
            Retry
          </button>
        </div>
      );
    default:
      return (
        <div className="flex min-h-screen items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
        </div>
      );
  }
}
