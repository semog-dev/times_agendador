import json
from pathlib import Path

_ARQUIVO = Path(__file__).parent / "processed_ids.json"


class StateStore:
    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if _ARQUIVO.exists():
            with open(_ARQUIVO, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._ids = set(data.get("processed_ids", []))
        else:
            self._persist()

    def _persist(self) -> None:
        with open(_ARQUIVO, "w", encoding="utf-8") as f:
            json.dump({"processed_ids": list(self._ids)}, f, indent=2, ensure_ascii=False)

    def is_processed(self, email_id: str) -> bool:
        return email_id in self._ids

    def mark_processed(self, email_id: str) -> None:
        self._ids.add(email_id)
        self._persist()
