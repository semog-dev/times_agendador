import email
import imaplib
import logging
import time
from email.header import decode_header

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 3
_BACKOFF_BASE_S = 2


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


def _buscar_emails(
    imap_host: str,
    imap_port: int,
    email_address: str,
    access_token: str,
    subject_filter: str,
    sender_domain: str,
) -> list[tuple[str, str]]:
    resultados: list[tuple[str, str]] = []

    with imaplib.IMAP4_SSL(imap_host, imap_port) as imap:
        auth_string = _xoauth2_string(email_address, access_token)
        imap.authenticate("XOAUTH2", lambda _: auth_string)
        imap.select("INBOX")

        criterio = f'(UNSEEN SUBJECT "{subject_filter}")'
        status, dados = imap.search(None, criterio)
        if status != "OK" or not dados[0]:
            logger.info("Nenhum email não lido encontrado com o filtro '%s'.", subject_filter)
            return resultados

        ids = dados[0].split()
        logger.info("%d email(s) encontrado(s) com o filtro.", len(ids))

        for email_id_bytes in ids:
            email_id = email_id_bytes.decode()
            status, msg_data = imap.fetch(email_id_bytes, "(RFC822)")
            if status != "OK":
                logger.warning("Não foi possível buscar o email ID %s.", email_id)
                continue

            raw_msg = msg_data[0][1]
            msg = email.message_from_bytes(raw_msg)

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

            # Marca como lido antes de fechar a conexão
            imap.store(email_id_bytes, "+FLAGS", "\\Seen")
            logger.info("Email ID %s marcado como lido.", email_id)

            resultados.append((email_id, html_body))

    return resultados


def fetch_unread_emails(
    imap_host: str,
    imap_port: int,
    email_address: str,
    access_token: str,
    subject_filter: str,
    sender_domain: str,
) -> list[tuple[str, str]]:
    """Busca emails não lidos via IMAP com retry e backoff exponencial."""
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
