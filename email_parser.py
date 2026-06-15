from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from models import DadosAula

_FUSO_BRT = ZoneInfo("America/Sao_Paulo")


def _extrair_campos(soup: BeautifulSoup) -> dict[str, BeautifulSoup]:
    """Mapeia texto do <th> (sem ':') para o elemento <td> correspondente."""
    campos: dict[str, BeautifulSoup] = {}
    for row in soup.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            chave = th.get_text(strip=True).rstrip(":")
            campos[chave] = td
    return campos


def _get_campo_texto(campos: dict[str, BeautifulSoup], nome: str) -> str:
    cel = campos.get(nome)
    if cel is None:
        raise ValueError(f"Campo obrigatório não encontrado na tabela do email: '{nome}'")
    return cel.get_text(strip=True)


def _extrair_link_zoom(soup: BeautifulSoup) -> str:
    # Tenta encontrar <a href="...zoom.us..."> em qualquer lugar do HTML
    tag_a = soup.find("a", href=lambda h: h and "zoom.us" in h)
    if tag_a:
        return tag_a["href"]

    # Fallback: texto da célula da linha com th "Link"
    for row in soup.find_all("tr"):
        th = row.find("th")
        if th and "Link" in th.get_text():
            td = row.find("td")
            return td.get_text(strip=True) if td else ""

    return ""


def parse_email(html_body: str, email_id: str, duracao_minutos: int) -> DadosAula:
    """Parseia o corpo HTML do email e retorna um DadosAula preenchido."""
    soup = BeautifulSoup(html_body, "html.parser")
    campos = _extrair_campos(soup)

    horario_str = _get_campo_texto(campos, "Horário")
    escola = _get_campo_texto(campos, "Escola")
    professor = _get_campo_texto(campos, "Professor(a)")
    tipo_aula = _get_campo_texto(campos, "Aula")
    link_zoom = _extrair_link_zoom(soup)

    try:
        horario_inicio = datetime.strptime(horario_str, "%d/%m/%Y às %H:%M").replace(
            tzinfo=_FUSO_BRT
        )
    except ValueError as exc:
        raise ValueError(
            f"Formato de horário inválido: '{horario_str}'. "
            "Esperado: 'dd/MM/yyyy às HH:mm'"
        ) from exc

    horario_fim = horario_inicio + timedelta(minutes=duracao_minutos)
    titulo = f"Aula Times Idiomas – {tipo_aula}"
    descricao = (
        f"Escola: {escola}\n"
        f"Professor(a): {professor}\n"
        f"Tipo de aula: {tipo_aula}\n"
        f"Horário: {horario_str}\n"
        f"Link: {link_zoom or 'não informado'}"
    )

    return DadosAula(
        titulo=titulo,
        horario_inicio=horario_inicio,
        horario_fim=horario_fim,
        escola=escola,
        professor=professor,
        tipo_aula=tipo_aula,
        link_zoom=link_zoom,
        descricao=descricao,
        email_id=email_id,
    )
