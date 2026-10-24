My finance AI agent kept getting the math wrong. Evals fixed it.

I'm building Bankr, an app where you ask plain-English questions about your money. "How much did I spend this month?" has exactly one right answer, so a confident, slightly wrong number is worse than no answer.

My early bugs all looked plausible:
• Paying off a credit card counted as $640 of extra spending
• A Venmo payback counted as income
• A savings transfer counted as both spending and income
• "Gas" included the PG&E utility bill

I caught them by luck. So I built an eval suite, following Anthropic's guidance on evals for AI agents. What worked:

1. Start from real failures. Every bug I fix becomes a test task.
2. Build a golden ledger. Expected figures are added up by hand, never computed by the code under test.
3. Plant traps. Each task checks for the right number and for the tempting wrong one.
4. Use plain-code graders first. Checking a dollar figure doesn't need an LLM judge.
5. Grade the outcome, not the path. A different-but-valid sequence of tool calls still passes.
6. Run every task several times. If the agent is right 75% of the time, three correct answers in a row happens only ~42% of the time. For money, all runs must pass (pass^k).
7. Split "must never break" from "still climbing." Regression tasks fail the build. Capability tasks are reported until they're reliable.
8. Read the transcripts. A failure is either an agent bug or a grader bug, and only the transcript tells you which.

The result: fixed bugs stay fixed, model and prompt changes become measurable experiments, and "it feels worse" turns into a number.

You don't need a platform to start. Write down the last five times your agent embarrassed you and turn each into a test.

What's the most confidently wrong thing your AI has said?

Full write-up and sources: Anthropic Engineering, "Demystifying evals for AI agents" (anthropic.com/engineering/demystifying-evals-for-ai-agents)

#AI #LLM #Evals #AIEngineering #Fintech #BuildInPublic
