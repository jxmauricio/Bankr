import { useEffect, useState } from "react";
import { fetchGoalProgress, fetchNetWorth } from "./lib/api";
import { useSession } from "./lib/session";
import { AuthPage } from "./pages/AuthPage";
import { LinkBankPage } from "./pages/LinkBankPage";
import { GoalSetupPage } from "./pages/GoalSetupPage";
import { HomePage } from "./pages/HomePage";
import { BootScreen } from "./components/BootScreen";

type OnboardingStep = "loading" | "link-bank" | "set-goal" | "home" | "load-failed";

export function App() {
  const { token, isAuthenticated } = useSession();

  if (!isAuthenticated) return <AuthPage />;
  return <PostSignInGate key={token} />;
}

function PostSignInGate() {
  const { token } = useSession();
  const [step, setStep] = useState<OnboardingStep>("loading");
  const [balancesRead, setBalancesRead] = useState(false);
  const [goalsRead, setGoalsRead] = useState(false);

  async function loadOnboardingState() {
    if (!token) return;
    setStep("loading");
    setBalancesRead(false);
    setGoalsRead(false);
    try {
      const [netWorth, goalProgress] = await Promise.all([
        fetchNetWorth(token).finally(() => setBalancesRead(true)),
        fetchGoalProgress(token).finally(() => setGoalsRead(true)),
      ]);
      if (netWorth.current === null) {
        setStep("link-bank");
      } else if (!goalProgress.goals?.length) {
        setStep("set-goal");
      } else {
        setStep("home");
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
    case "home":
      return <HomePage onNoBanksLeft={loadOnboardingState} />;
    case "set-goal":
      return <GoalSetupPage onGoalSet={() => setStep("home")} />;
    case "link-bank":
      return <LinkBankPage onLinked={() => setStep("set-goal")} />;
    case "load-failed":
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
          <p className="text-ink-soft">Couldn't reach Bankr.</p>
          <button
            type="button"
            onClick={loadOnboardingState}
            className="rounded-[14px] bg-accent px-4 py-2 text-sm font-medium text-bg hover:bg-accent-strong cursor-pointer"
          >
            Retry
          </button>
        </div>
      );
    default:
      return (
        <BootScreen
          steps={[
            { label: "signed in", state: "done" },
            { label: "reading balances", state: balancesRead ? "done" : "active" },
            { label: "loading goals", state: goalsRead ? "done" : "active" },
          ]}
        />
      );
  }
}
