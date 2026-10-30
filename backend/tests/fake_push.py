from app.integrations.push import PushMessage, PushResult


class FakePushSender:
    """Records what would have been pushed -- never touches Expo's API. Same
    role tests/fake_aggregator.py plays for Plaid."""

    def __init__(self, dead_tokens: set[str] | None = None):
        self.sent: list[PushMessage] = []
        self.dead_tokens = dead_tokens or set()

    def send(self, messages: list[PushMessage]) -> PushResult:
        live = [m for m in messages if m.token not in self.dead_tokens]
        self.sent += live
        return PushResult(sent=len(live), dead_tokens=[m.token for m in messages if m.token in self.dead_tokens])
