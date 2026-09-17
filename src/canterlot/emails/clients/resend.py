import resend
from resend.exceptions import RateLimitError, ResendError

from canterlot.utils import get_logger

from ..interfaces import EmailClient, EmailMessage, EmailSendResult

logger = get_logger(__name__)


class ResendEmailClient(EmailClient):
    def __init__(self, api_key: str):
        self.__api_key = api_key
        resend.api_key = self.__api_key

    @property
    def name(self) -> str:
        return "resend"

    async def send(self, message: EmailMessage) -> EmailSendResult:
        log = logger.bind(provider=self.name, recipient_count=len(message.to))

        payload: resend.Emails.SendParams = {
            "from": message.sender,
            "to": message.to,
            "subject": message.subject,
            "html": message.html,
            "reply_to": message.reply_to,
        }

        if message.headers:
            payload["headers"] = message.headers

        try:
            response = await resend.Emails.send_async(payload)
        except RateLimitError as exc:
            log.warning("Resend API rate limit tripped (429). Triggering queue throttling.")
            return EmailSendResult(
                success=False,
                error_message=str(exc),
                disabled=True,
            )
        except ResendError as exc:
            log.error("Resend send failed with SDK error", error_type=type(exc).__name__, exc_info=True)
            return EmailSendResult(success=False, error_message=str(exc))

        except Exception as exc:
            log.error(
                "Resend send encountered an unexpected infrastructure failure",
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return EmailSendResult(success=False, error_message=str(exc))

        message_id = response.get("id")
        log.info("Resend send succeeded", message_id=message_id)

        return EmailSendResult(success=True, provider_message_id=message_id, disabled=False)
