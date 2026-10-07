import email
import hashlib
import imaplib
import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from email.header import decode_header

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 3
_BACKOFF_BASE_S = 2
_MESES_IMAP = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _decodificar_header(valor: str) -> str:
    partes = decode_header(valor)
    resultado = []
    for parte, charset in partes:
        if isinstance(parte, bytes):
            resultado.append(parte.decode(charset or "utf-8", errors="replace"))
        else:
            resultado.append(parte)
    return "".join(resultado)


def _extrair_html(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for parte in msg.walk():
            if parte.get_content_type() == "text/html":
                payload = parte.get_payload(decode=True)
                charset = parte.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    elif msg.get_content_type() == "text/html":
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def _xoauth2_string(email_address: str, access_token: str) -> bytes:
    return f"user={email_address}\x01auth=Bearer {access_token}\x01\x01".encode()


def _data_imap(dias_atras: int) -> str:
    # Formato exigido pelo IMAP (ex.: 06-Oct-2026); mês sempre em inglês, independente do locale
    data = date.today() - timedelta(days=dias_atras)
    return f"{data.day:02d}-{_MESES_IMAP[data.month - 1]}-{data.year}"


def _buscar_emails(
    imap_host: str,
    imap_port: int,
    email_address: str,
    access_token: str,
    subject_filter: str,
    sender_domain: str,
    janela_dias: int,
    ja_processado: Callable[[str], bool],
) -> list[tuple[str, str]]:
    resultados: list[tuple[str, str]] = []

    with imaplib.IMAP4_SSL(imap_host, imap_port) as imap:
        auth_string = _xoauth2_string(email_address, access_token)
        imap.authenticate("XOAUTH2", lambda _: auth_string)
        # Somente leitura: não altera a flag de lido dos emails
        imap.select("INBOX", readonly=True)

        # Não filtra por UNSEEN: o email pode ter sido aberto em outro cliente antes do ciclo
        criterio = f'(SINCE "{_data_imap(janela_dias)}" SUBJECT "{subject_filter}")'
        status, dados = imap.search(None, criterio)
        if status != "OK" or not dados[0]:
            logger.info(
                "Nenhum email encontrado com o filtro '%s' nos últimos %d dia(s).",
                subject_filter,
                janela_dias,
            )
            return resultados

        ids = dados[0].split()
        logger.info("%d email(s) encontrado(s) com o filtro.", len(ids))

        for seq_bytes in ids:
            seq = seq_bytes.decode()
            status, msg_data = imap.fetch(seq_bytes, "(BODY.PEEK[])")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                logger.warning("Não foi possível buscar o email de sequência %s.", seq)
                continue

            raw_msg = msg_data[0][1]
            msg = email.message_from_bytes(raw_msg)

            # O número de sequência IMAP é reatribuído quando mensagens são removidas;
            # o Message-ID é o identificador estável usado na deduplicação
            email_id = (msg.get("Message-ID") or "").strip() or hashlib.sha256(raw_msg).hexdigest()
            if ja_processado(email_id):
                logger.debug("Email %s já processado. Ignorando.", email_id)
                continue

            remetente = _decodificar_header(msg.get("From", ""))
            if sender_domain and sender_domain.lower() not in remetente.lower():
                logger.debug(
                    "Email ID %s ignorado — remetente '%s' fora do domínio '%s'.",
                    email_id,
                    remetente,
                    sender_domain,
                )
                continue

            html_body = _extrair_html(msg)
            if not html_body:
                logger.warning("Email ID %s não possui corpo HTML. Ignorando.", email_id)
                continue

            resultados.append((email_id, html_body))

    return resultados


def fetch_pending_emails(
    imap_host: str,
    imap_port: int,
    email_address: str,
    access_token: str,
    subject_filter: str,
    sender_domain: str,
    janela_dias: int,
    ja_processado: Callable[[str], bool],
) -> list[tuple[str, str]]:
    """Busca emails recentes ainda não processados via IMAP com retry e backoff exponencial."""
    ultimo_erro: Exception | None = None

    for tentativa in range(1, _MAX_TENTATIVAS + 1):
        try:
            return _buscar_emails(
                imap_host,
                imap_port,
                email_address,
                access_token,
                subject_filter,
                sender_domain,
                janela_dias,
                ja_processado,
            )
        except Exception as exc:
            ultimo_erro = exc
            if tentativa == _MAX_TENTATIVAS:
                break
            espera = _BACKOFF_BASE_S ** tentativa
            logger.warning(
                "Tentativa %d/%d falhou: %s. Aguardando %ds...",
                tentativa,
                _MAX_TENTATIVAS,
                exc,
                espera,
            )
            time.sleep(espera)

    raise RuntimeError(
        f"Falha ao conectar ao IMAP após {_MAX_TENTATIVAS} tentativas."
    ) from ultimo_erro
