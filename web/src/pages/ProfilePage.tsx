import { useEffect, useState } from "react";
import { fetchProfile, type Profile } from "../lib/api";
import { useSession } from "../lib/session";
import { AuthPage } from "./AuthPage";

export function ProfilePage() {
  const { token, isAuthenticated, signOut } = useSession();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchProfile(token)
      .then(setProfile)
      .catch(() => setFailed(true));
  }, [token]);

  if (!isAuthenticated) return <AuthPage />;

  return (
    <div className="min-h-screen px-6 py-12">
      <main className="mx-auto max-w-2xl">
        <a href="/" className="text-sm text-ink-soft transition-colors hover:text-ink">
          ← Back to Bankr
        </a>
        <h1 className="mt-6 font-display text-3xl font-semibold tracking-tight text-ink">My profile</h1>
        <div className="mt-8">
          <p className="text-sm text-ink-faint">Email</p>
          {failed ? (
            <p className="mt-1 text-ink-soft">
              Couldn't load your profile.{" "}
              <button type="button" onClick={signOut} className="text-accent underline cursor-pointer">
                Sign out
              </button>
            </p>
          ) : (
            <p className="mt-1 text-lg text-ink">{profile?.email ?? "…"}</p>
          )}
        </div>
      </main>
    </div>
  );
}
