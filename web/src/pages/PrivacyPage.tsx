import type { ReactNode } from "react";

// Keep this page true to the code. If you change what's stored (backend
// models), who receives data (Plaid, the AI model, hosting, Sentry), or what
// deleting does (backend/app/services/account_removal.py), update it here.
const LAST_UPDATED = "October 3, 2026";
const CONTACT_EMAIL = import.meta.env.VITE_CONTACT_EMAIL as string | undefined;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-3 space-y-3 text-ink-soft leading-relaxed">{children}</div>
    </section>
  );
}

function List({ items }: { items: ReactNode[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

export function PrivacyPage() {
  return (
    <div className="min-h-screen px-6 py-12">
      <main className="mx-auto max-w-2xl">
        <a href="/" className="text-sm text-ink-soft transition-colors hover:text-ink">
          ← Back to Bankr
        </a>
        <h1 className="mt-6 font-display text-3xl font-semibold tracking-tight text-ink">Privacy notice</h1>
        <p className="mt-2 text-sm text-ink-faint">Last updated {LAST_UPDATED}</p>

        <p className="mt-6 text-ink-soft leading-relaxed">
          Bankr is a personal finance app in a private beta, run by an individual rather than a company. It connects to
          your bank, shows your net worth and spending, and lets you ask an AI assistant about your money. This page
          explains what it keeps, who else sees it, and how to get rid of it. It is written to match what the app
          actually does.
        </p>

        <Section title="What Bankr collects">
          <List
            items={[
              <>
                <strong className="text-ink">Your account:</strong> your email address and your password, which is stored
                only as a one-way hash, never in readable form.
              </>,
              <>
                <strong className="text-ink">Your bank data, through Plaid:</strong> account names, the last four digits,
                balances, and transactions (date, amount, merchant, category). Bankr asks for read-only access. It can't
                move money. Your bank username and password go to Plaid and your bank, never to Bankr.
              </>,
              <>
                <strong className="text-ink">Bank access tokens:</strong> the key Plaid gives Bankr to keep your accounts
                up to date. It is encrypted before it is stored.
              </>,
              <>
                <strong className="text-ink">What you create:</strong> your goals, a daily net-worth history Bankr
                calculates, short alerts it generates about your accounts, and your chat messages and the assistant's
                replies, including which data lookups were used to answer.
              </>,
              <>
                <strong className="text-ink">Your time zone,</strong> sent by your browser, so "this month" starts on the
                right day for you.
              </>,
              <>
                <strong className="text-ink">In your browser:</strong> a sign-in token and your last conversation, kept in
                local storage on your device. Bankr has no advertising or analytics trackers.
              </>,
            ]}
          />
        </Section>

        <Section title="Who else sees your data">
          <p>Bankr uses these services to run. None of them is given your data to sell or advertise with.</p>
          <List
            items={[
              <>
                <strong className="text-ink">Plaid</strong> connects your bank and supplies your balances and
                transactions. Plaid's own{" "}
                <a className="text-accent underline" href="https://plaid.com/legal/#end-user-privacy-policy">
                  privacy policy
                </a>{" "}
                applies to what it collects from you.
              </>,
              <>
                <strong className="text-ink">The AI model.</strong> When you ask the assistant something, Bankr sends your
                question, your recent messages (up to the last 20), and the results of the lookups it runs to answer, such
                as balances or transactions, to OpenRouter, which passes them to the AI model Bankr uses (currently
                DeepSeek's). The same applies to the short alerts Bankr writes about your accounts. Your bank login and
                access token are never sent.
              </>,
              <>
                <strong className="text-ink">Web search.</strong> For general facts like current savings rates, the
                assistant can run a web search. It is instructed to search only for general information, never about you,
                but the AI writes the search itself, so treat anything you type in chat as something that could appear in
                one.
              </>,
              <>
                <strong className="text-ink">Hosting:</strong> Render runs the server, Supabase stores the database, and
                Vercel serves the website. Your data is stored with them on Bankr's behalf.
              </>,
              <>
                <strong className="text-ink">Error reports:</strong> if something breaks, Sentry receives a technical
                error report. Bankr configures it to leave out chat messages, request contents, balances, transactions,
                and your email address.
              </>,
              <>
                <strong className="text-ink">Voice mode:</strong> if you use the microphone, your browser's own speech
                service (for example Google's in Chrome) turns your voice into text. Bankr receives only the text.
              </>,
            ]}
          />
        </Section>

        <Section title="How long it is kept, and how to delete it">
          <p>
            Bankr keeps your data until you delete it. In <strong className="text-ink">Settings</strong> you can:
          </p>
          <List
            items={[
              <>
                <strong className="text-ink">Disconnect a bank.</strong> Bankr tells Plaid to drop the connection and
                deletes that bank's accounts and transactions. If it was your last bank, your net-worth history goes too.
              </>,
              <>
                <strong className="text-ink">Delete your account.</strong> After you confirm with your password, Bankr
                disconnects every bank and permanently erases your goals, history, alerts, chat messages, and the account
                itself.
              </>,
            ]}
          />
          <p>
            Two limits: Plaid keeps its own records under its own policy, and database backups held by Bankr's hosting
            provider may contain your data for a limited time after you delete it.
          </p>
        </Section>

        <Section title="Security">
          <p>
            Traffic to Bankr is encrypted in transit, passwords are hashed, and bank access tokens are encrypted before
            they are stored. Bankr is a small beta run by one person, so no security is perfect. If you notice anything
            wrong, please say so.
          </p>
        </Section>

        <Section title="The assistant is not a financial advisor">
          <p>
            The AI can be wrong, including about numbers. Check anything important against your bank, and don't treat its
            answers as financial, tax, or legal advice.
          </p>
        </Section>

        <Section title="Changes and questions">
          <p>
            If this notice changes in a way that matters, the date at the top will change.{" "}
            {CONTACT_EMAIL ? (
              <>
                Questions or requests about your data: <a className="text-accent underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
              </>
            ) : (
              <>For questions or requests about your data, contact the person who invited you to Bankr.</>
            )}
          </p>
        </Section>
      </main>
    </div>
  );
}
