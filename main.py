import logging
import os
import sys
import time

from dotenv import load_dotenv

from calendar_service import CalendarService
from email_parser import parse_email
from imap_reader import fetch_unread_emails
from models import DadosAula
from state_store import StateStore

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("times_agendador")

_INTERVALO_S = int(os.getenv("RUN_INTERVAL_SECONDS", "600"))


def _env_obrigatorio(chave: str) -> str:
    valor = os.getenv(chave, "").strip()
    if not valor:
        logger.error("Variável de ambiente obrigatória ausente ou vazia: %s", chave)
        sys.exit(1)
    return valor


def _executar_ciclo(
    imap_host: str,
    imap_port: int,
    email_address: str,
    subject_filter: str,
    sender_domain: str,
    duracao_minutos: int,
    calendar_service: CalendarService,
    state_store: StateStore,
) -> None:
    imap_token = calendar_service.get_imap_token()
    if not imap_token:
        logger.error("Não foi possível obter token IMAP.")
        return

    logger.info("Buscando emails não processados na caixa de entrada...")
    try:
        emails = fetch_unread_emails(
            imap_host=imap_host,
            imap_port=imap_port,
            email_address=email_address,
            access_token=imap_token,
            subject_filter=subject_filter,
            sender_domain=sender_domain,
        )
    except RuntimeError as exc:
        logger.error("Erro ao acessar o IMAP: %s", exc)
        return

    if not emails:
        logger.info("Nenhum email novo encontrado.")
        return

    processados = 0
    erros = 0

    for email_id, html_body in emails:
        logger.info("--- Processando email ID: %s ---", email_id)

        if state_store.is_processed(email_id):
            logger.info("Email ID %s já foi processado anteriormente. Ignorando.", email_id)
            continue

        try:
            dados_aula: DadosAula = parse_email(html_body, email_id, duracao_minutos)
            logger.info(
                "Aula parseada: '%s' em %s.",
                dados_aula.titulo,
                dados_aula.horario_inicio.strftime("%d/%m/%Y %H:%M"),
            )
        except ValueError as exc:
            logger.error("Erro ao parsear email ID %s: %s", email_id, exc)
            erros += 1
            continue

        sucesso = calendar_service.create_event(dados_aula)
        if sucesso:
            state_store.mark_processed(email_id)
            processados += 1
        else:
            logger.error(
                "Falha ao criar evento para email ID %s. Tentará novamente no próximo ciclo.",
                email_id,
            )
            erros += 1

    logger.info("Ciclo concluído: %d evento(s) criado(s), %d erro(s).", processados, erros)


def main() -> None:
    logger.info("=== Times Agendador iniciado (intervalo: %ds) ===", _INTERVALO_S)

    imap_host = os.getenv("IMAP_HOST", "outlook.office365.com")
    imap_port = int(os.getenv("IMAP_PORT", "993"))
    email_address = _env_obrigatorio("OUTLOOK_EMAIL")
    subject_filter = os.getenv("SUBJECT_FILTER", "Informativo - Aula agendada")
    sender_domain = os.getenv("SENDER_DOMAIN", "timesidiomas")
    client_id = _env_obrigatorio("AZURE_CLIENT_ID")
    duracao_minutos = int(os.getenv("DURACAO_AULA_MINUTOS", "50"))

    state_store = StateStore()
    calendar_service = CalendarService(client_id)

    if not calendar_service.authenticate():
        logger.error("Autenticação falhou. Encerrando.")
        sys.exit(1)

    while True:
        try:
            _executar_ciclo(
                imap_host=imap_host,
                imap_port=imap_port,
                email_address=email_address,
                subject_filter=subject_filter,
                sender_domain=sender_domain,
                duracao_minutos=duracao_minutos,
                calendar_service=calendar_service,
                state_store=state_store,
            )
        except Exception as exc:
            logger.error("Erro inesperado no ciclo: %s", exc, exc_info=True)

        logger.info("Aguardando %ds até a próxima verificação...", _INTERVALO_S)
        time.sleep(_INTERVALO_S)


if __name__ == "__main__":
    main()
