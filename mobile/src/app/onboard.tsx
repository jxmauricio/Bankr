import { useRouter } from "expo-router";
import { Onboarding } from "@/features/onboarding/Onboarding";
import { useSession } from "@/lib/session";

/** Logged-out questionnaire. Signup happens on the last step, then the session starts. */
export default function OnboardScreen() {
  const router = useRouter();
  const { signIn } = useSession();
  return (
    <Onboarding
      onExit={() => router.replace("/")}
      onDone={(sessionToken) => {
        if (sessionToken) signIn(sessionToken);
      }}
    />
  );
}
