# My finance chatbot kept getting the math wrong. Here's how evals fixed it.

When you ask a money app "How much did I spend this month?", there is exactly one right answer. That makes it a brutal place to ship an AI agent. A friendly, confident, slightly wrong number is worse than no answer at all.

I'm building Bankr, an app that connects to your bank accounts and lets you ask questions about your money in plain English. Under the hood, an LLM agent calls tools that query your transactions. Early on, I tested it the way most people do: ask a few questions, eyeball the replies, ship. It worked right up until it didn't.

The bugs I found were never "the model is dumb." They were subtle:

- Paying off a credit card showed up as $640 of extra spending, even though the card purchases were already counted.
- A friend paying me back on Venmo counted as income.
- Moving $500 to savings counted as both spending and income.
- "Gas last month" included the PG&E utility bill.

Every one of these looked plausible. I only caught them by luck. So I stopped relying on luck and built an eval suite, following the guidance in Anthropic's engineering post, [Demystifying evals for AI agents](https://anthropic.com/engineering/demystifying-evals-for-ai-agents), and their [docs on building evals](https://platform.claude.com/docs/en/docs/test-and-evaluate/develop-tests).

Here's what I did and what I'd tell anyone building an agent.

## 1. Start from real failures, not a grand design

Anthropic's advice is to start early. A few dozen tasks drawn from real failures beat a perfect framework you never build. My first tasks were simply the bugs above, turned into test cases. My rule now: **every bug I fix in the agent becomes an eval task.** The suite grows exactly where the product has actually broken.

## 2. Give every task one answer two experts would agree on

The post stresses unambiguous tasks with a known-good reference. For a finance app, I can do this literally. I built a small "golden ledger": a hand-authored set of accounts and transactions with a frozen "today." Every expected figure (net worth, groceries last month, dining last week) was added up by hand, **never computed by the code under test.** If the agent and my code disagree, the human arithmetic wins.

I also planted traps in the ledger on purpose: the card payment, the Venmo payback, the savings transfer, the refund that needs to be netted out. Each task checks for the right number and also that the tempting wrong number never appears.

## 3. Use deterministic graders where you can

Anthropic describes three grader types: code-based (fast, cheap, objective, but brittle), model-based (flexible, but non-deterministic and needing calibration), and human (the gold standard, but slow). Money questions are lucky, because most answers are checkable with plain code:

- `says_amount(expected)`: the right figure is in the reply.
- `never_says_amount(trap)`: the naive wrong total isn't.
- `figures_cited()`: every dollar figure traces back to a tool result, so the agent can't invent a number.
- `called_no_tools()`: replying "Thanks!" shouldn't trigger a database query.

No LLM judge, no vibes, no cost per grade.

## 4. Grade the outcome, not the path

One of the post's best tips is to grade what the agent produced, not the route it took. My graders never check the order of tool calls. If the agent reaches the correct, cited answer through a different sequence of tools than I expected, it still passes. Rigid path checks make evals brittle and punish good behavior you didn't anticipate.

## 5. Include the "should NOT happen" cases

Good eval sets are balanced: they test when a behavior should occur and when it shouldn't. Mine include:

- A question about pet spending when the ledger has none. The only acceptable dollar figure is zero. Anything else is invented.
- "Should I put my savings into Tesla stock?" The agent must not give specific investment advice.
- "Thanks!" The agent should just say you're welcome.

## 6. Run each task several times

LLMs are non-deterministic, so one pass proves little. Anthropic distinguishes two metrics:

- **pass@k**: at least one of k trials succeeded.
- **pass^k**: all k trials succeeded.

For a user-facing answer about someone's money, pass^k is the bar. If the agent is right 75% of the time, three correct answers in a row happens only about 42% of the time. Users don't get to pick the lucky run. My suite runs each task 3 times by default and requires all of them to pass.

## 7. Separate "must never break" from "still climbing"

I split tasks into two suites. **Regression** tasks must pass every trial, and a failure fails the run. **Capability** tasks are targets I'm still working toward, such as asking a clarifying question when "gas" is ambiguous. They're reported but don't fail the build. When a capability task passes reliably, it graduates to regression. It mirrors the capability-versus-regression split in Anthropic's post.

## 8. Read the transcripts

I'm quoting Anthropic here because it's the line that matters most: "Read the transcripts!" Every trial saves the full reply and tool-call log. A failed check means one of two things: the agent is wrong, or my grader is wrong. Only the transcript tells you which. A score alone can mislead you in either direction.

## What changed

A few things shifted once the suite existed:

- **Fixes stopped regressing.** A bug fixed once stays fixed, because the task is still there.
- **Model and prompt changes became cheap to judge.** Swapping a model or editing the system prompt is a measurable experiment, not a gamble.
- **"It feels worse" became a number.**
- **I found out which of my checks were weak.** My advice-decline grader is a regex, a crude proxy. That's now a flagged candidate for a calibrated LLM judge with human spot-checks, exactly the layering Anthropic recommends.

Evals also aren't the whole safety net. Anthropic is clear that they sit alongside production monitoring, user feedback and manual review, like slices of Swiss cheese where each layer catches what another misses. In Bankr, evals sit next to in-app citations that mark each number as verified against the underlying data.

## If you're building an agent, start here

1. Write down the last five times your agent embarrassed you.
2. Turn each into a task with an answer you computed yourself.
3. Add one trap per task: the wrong answer a naive approach would give.
4. Grade the outcome with plain code first.
5. Run each task more than once.
6. Read the failures.

You don't need a platform or a team to begin. You need a handful of honest test cases and the discipline to add one every time something breaks.

*What's the worst thing your AI feature has gotten confidently wrong? I'd love to hear it.*

---

**Sources**
- Anthropic Engineering, [Demystifying evals for AI agents](https://anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Anthropic, [Define success criteria and build evaluations](https://platform.claude.com/docs/en/docs/test-and-evaluate/develop-tests)

#AI #LLM #Evals #AIEngineering #Fintech #BuildInPublic
