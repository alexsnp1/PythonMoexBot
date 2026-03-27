from __future__ import annotations

import threading


class UserChatRegistry:
    """
    In-memory map: user_id -> last known chat_id.
    Used for sending notifications without DB schema changes.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._user_to_chat: dict[int, int] = {}

    def remember(self, user_id: int, chat_id: int) -> None:
        with self._lock:
            self._user_to_chat[user_id] = chat_id

    def get_chat_id(self, user_id: int) -> int | None:
        with self._lock:
            return self._user_to_chat.get(user_id)

