import logging
import os

import msal
import requests

from models import DadosAula
from state_store import get_data_dir

logger = logging.getLogger(__name__)

_GRAPH_SCOPES = ["https://graph.microsoft.com/Calendars.ReadWrite"]
_IMAP_SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All"]
_CACHE_FILENAME = "o365_token.txt"
_AUTHORITY = "https://login.microsoftonline.com/consumers"
_GRAPH_URL = "https://graph.microsoft.com/v1.0"
_TIMEZONE = "America/Sao_Paulo"


class CalendarService:
    def __init__(self, client_id: str) -> None:
        self._cache_file = get_data_dir() / _CACHE_FILENAME
        self._cache = msal.SerializableTokenCache()
        # O arquivo é atualizado a cada renovação de token; MSAL_TOKEN_CACHE é só a semente inicial
        cache_env = os.getenv("MSAL_TOKEN_CACHE")
        if self._cache_file.exists():
            self._cache.deserialize(self._cache_file.read_text(encoding="utf-8"))
        elif cache_env:
            self._cache.deserialize(cache_env)

        self._app = msal.PublicClientApplication(
            client_id,
            authority=_AUTHORITY,
            token_cache=self._cache,
        )

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            self._cache_file.write_text(self._cache.serialize(), encoding="utf-8")

    def _get_token(self) -> str | None:
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(_GRAPH_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        return None

    def get_imap_token(self) -> str | None:
        """Retorna token OAuth2 para autenticação IMAP XOAUTH2.

        Tenta silenciosamente primeiro; se o usuário ainda não deu consentimento
        para o escopo IMAP, inicia um novo Device Code Flow para obtê-lo.
        """
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(_IMAP_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]

        logger.info("Consentimento para acesso ao IMAP necessário. Siga as instruções abaixo.")
        flow = self._app.initiate_device_flow(scopes=_IMAP_SCOPES)
        if "user_code" not in flow:
            logger.error("Falha ao iniciar Device Code Flow para IMAP: %s", flow.get("error_description"))
            return None

        # Via logger (e não print) para o código aparecer no log do container
        logger.info(flow["message"])
        result = self._app.acquire_token_by_device_flow(flow)
        if result and "access_token" in result:
            self._save_cache()
            logger.info("Acesso ao IMAP autorizado.")
            return result["access_token"]

        logger.error("Falha na autenticação IMAP: %s", result.get("error_description"))
        return None

    def authenticate(self) -> bool:
        """Autentica via Device Code Flow; reutiliza token salvo se válido."""
        if self._get_token():
            logger.info("Token existente válido. Nenhuma nova autenticação necessária.")
            return True

        flow = self._app.initiate_device_flow(scopes=_GRAPH_SCOPES)
        if "user_code" not in flow:
            logger.error("Falha ao iniciar Device Code Flow: %s", flow.get("error_description"))
            return False

        logger.info("Iniciando autenticação via Device Code Flow. Siga as instruções abaixo.")
        logger.info(flow["message"])

        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self._save_cache()
            logger.info("Autenticação concluída. Token salvo em '%s'.", self._cache_file)
            return True

        logger.error("Falha na autenticação: %s", result.get("error_description"))
        return False

    def _event_exists(self, token: str, dados: DadosAula) -> bool:
        """Verifica se já há evento com o mesmo título no horário da aula.

        Protege contra duplicatas quando o processed_ids.json é perdido (ex.: redeploy).
        Lança exceção se a consulta falhar, para que o evento não seja criado às cegas.
        """
        response = requests.get(
            f"{_GRAPH_URL}/me/calendarView",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "startDateTime": dados.horario_inicio.isoformat(),
                "endDateTime": dados.horario_fim.isoformat(),
                "$select": "subject",
                "$top": "50",
            },
            timeout=30,
        )
        response.raise_for_status()
        return any(
            evento.get("subject") == dados.titulo
            for evento in response.json().get("value", [])
        )

    def create_event(self, dados: DadosAula) -> bool:
        """Cria um evento no calendário padrão do Outlook. Retorna True em caso de sucesso."""
        try:
            if not self.authenticate():
                return False

            token = self._get_token()
            if not token:
                logger.error("Não foi possível obter token de acesso.")
                return False

            if self._event_exists(token, dados):
                logger.info(
                    "Evento '%s' em %s já existe no calendário. Nada a criar.",
                    dados.titulo,
                    dados.horario_inicio.strftime("%d/%m/%Y %H:%M"),
                )
                return True

            corpo = dados.descricao
            if dados.link_zoom:
                corpo += f"\n\nLink da aula: {dados.link_zoom}"

            payload = {
                "subject": dados.titulo,
                "start": {
                    "dateTime": dados.horario_inicio.isoformat(),
                    "timeZone": _TIMEZONE,
                },
                "end": {
                    "dateTime": dados.horario_fim.isoformat(),
                    "timeZone": _TIMEZONE,
                },
                "location": {"displayName": dados.escola},
                "body": {"contentType": "text", "content": corpo},
                "isReminderOn": True,
                "reminderMinutesBeforeStart": 15,
            }

            response = requests.post(
                f"{_GRAPH_URL}/me/events",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )

            if response.status_code == 201:
                logger.info(
                    "Evento criado com sucesso: '%s' em %s.",
                    dados.titulo,
                    dados.horario_inicio.strftime("%d/%m/%Y %H:%M"),
                )
                return True

            logger.error(
                "Erro ao criar evento: HTTP %d — %s", response.status_code, response.text
            )
            return False

        except Exception as exc:
            logger.error("Erro ao criar evento '%s': %s", dados.titulo, exc)
            return False
