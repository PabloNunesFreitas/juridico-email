"""Estado in-memory da sincronização atual (para exibir progresso na UI)."""
import threading
from datetime import datetime
from typing import Optional


class SyncState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running: bool = False
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.scanned: int = 0
        self.to_fetch: int = 0
        self.fetched: int = 0
        self.new_messages: int = 0
        self.new_demands: int = 0
        self.error: Optional[str] = None
        self.last_message: Optional[str] = None  # subject ou descrição curta

    def try_start(self) -> bool:
        """Atomic: marca como rodando se não estiver. Retorna False se já rodando."""
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.started_at = datetime.utcnow()
            self.finished_at = None
            self.scanned = 0
            self.to_fetch = 0
            self.fetched = 0
            self.new_messages = 0
            self.new_demands = 0
            self.error = None
            self.last_message = None
            return True

    def start(self) -> None:
        with self._lock:
            self.running = True
            self.started_at = datetime.utcnow()
            self.finished_at = None
            self.scanned = 0
            self.to_fetch = 0
            self.fetched = 0
            self.new_messages = 0
            self.new_demands = 0
            self.error = None
            self.last_message = None

    def set_total(self, scanned: int, to_fetch: int) -> None:
        with self._lock:
            self.scanned = scanned
            self.to_fetch = to_fetch

    def tick(self, fetched: int, new_messages: int, new_demands: int, last: Optional[str] = None) -> None:
        with self._lock:
            self.fetched = fetched
            self.new_messages = new_messages
            self.new_demands = new_demands
            if last:
                self.last_message = last[:120]

    def finish(self, error: Optional[str] = None) -> None:
        with self._lock:
            self.running = False
            self.finished_at = datetime.utcnow()
            self.error = error

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None,
                "scanned": self.scanned,
                "to_fetch": self.to_fetch,
                "fetched": self.fetched,
                "new_messages": self.new_messages,
                "new_demands": self.new_demands,
                "error": self.error,
                "last_message": self.last_message,
            }


SYNC_STATE = SyncState()
