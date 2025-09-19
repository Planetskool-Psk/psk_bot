"""Session-scoped conversation history management."""

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque, Dict, List


@dataclass
class ConversationTurn:
    user: str
    bot: str


@dataclass
class ConversationHistory:
    max_length: int
    _turns: Deque[ConversationTurn] = field(init=False)

    def __post_init__(self) -> None:
        self._turns = deque(maxlen=self.max_length)

    def add_turn(self, user: str, bot: str) -> None:
        self._turns.append(ConversationTurn(user=user, bot=bot))

    def as_dicts(self) -> List[Dict[str, str]]:
        return [
            {"user": turn.user, "bot": turn.bot}
            for turn in self._turns
        ]


class ConversationStore:
    """Thread-safe store for per-session conversation histories."""

    def __init__(self, max_length: int) -> None:
        self._max_length = max_length
        self._histories: Dict[str, ConversationHistory] = {}
        self._lock = Lock()

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._histories[session_id] = ConversationHistory(max_length=self._max_length)

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._histories.pop(session_id, None)

    def append_turn(self, session_id: str, user: str, bot: str) -> None:
        with self._lock:
            history = self._histories.setdefault(
                session_id,
                ConversationHistory(max_length=self._max_length),
            )
            history.add_turn(user=user, bot=bot)

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            history = self._histories.get(session_id)
            return history.as_dicts() if history else []
