import json
import os
from pathlib import Path


def get_data_dir() -> Path:
    """Diretório dos arquivos persistentes (token e IDs processados).

    Configurável via DATA_DIR para apontar para um volume em ambientes com
    filesystem efêmero (ex.: Railway). Padrão: pasta do script.
    """
    caminho = Path(os.getenv("DATA_DIR") or Path(__file__).parent)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


class StateStore:
    def __init__(self) -> None:
        self._arquivo = get_data_dir() / "processed_ids.json"
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self._arquivo.exists():
            with open(self._arquivo, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._ids = set(data.get("processed_ids", []))
        else:
            self._persist()

    def _persist(self) -> None:
        with open(self._arquivo, "w", encoding="utf-8") as f:
            json.dump({"processed_ids": list(self._ids)}, f, indent=2, ensure_ascii=False)

    def is_processed(self, email_id: str) -> bool:
        return email_id in self._ids

    def mark_processed(self, email_id: str) -> None:
        self._ids.add(email_id)
        self._persist()
