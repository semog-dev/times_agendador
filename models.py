from dataclasses import dataclass
from datetime import datetime


@dataclass
class DadosAula:
    titulo: str
    horario_inicio: datetime
    horario_fim: datetime
    escola: str
    professor: str
    tipo_aula: str
    link_zoom: str
    descricao: str
    email_id: str
