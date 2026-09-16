from typing import Any, cast

from structlog.testing import capture_logs

from canterlot.emails import EmailMessage, Templates, render_email_template
from canterlot.emails.clients import DryRunEmailClient
from canterlot.emails.core.schemas import EmailVerificationContext, InviteInternalContext
from tools.factories.emails import EmailVerificationContextFactory, InviteInternalContextFactory


def describe_send():
    async def it_returns_a_successful_dry_run_result():
        client = DryRunEmailClient()

        result = await client.send(
            EmailMessage(
                sender="Canterlot <onboarding@resend.dev>",
                to=["delivered@resend.dev"],
                subject="Hello",
                html="<p>Hello</p>",
                reply_to="support@canterlot.com.br",
            )
        )

        assert result.success is True
        assert result.dry_run is True
        assert result.disabled is False
        assert result.provider_message_id is None

    async def it_logs_the_debug_context_alongside_the_existing_metadata():
        client = DryRunEmailClient()
        debug_context = {"code": "123456", "action_url": "https://canterlot.com.br/verify-email?token=abc"}

        with capture_logs() as logs:
            await client.send(
                EmailMessage(
                    sender="Canterlot <onboarding@resend.dev>",
                    to=["delivered@resend.dev"],
                    subject="Hello",
                    html="<p>Hello</p>",
                    reply_to="support@canterlot.com.br",
                    headers={"List-Unsubscribe": "<https://example.com/u/tok>"},
                    debug_context=debug_context,
                )
            )

        assert len(logs) == 1
        log = logs[0]
        assert log["debug_context"] == debug_context
        assert log["recipient_count"] == 1
        assert log["subject"] == "Hello"
        assert log["has_reply_to"] is True
        assert log["has_headers"] is True

    async def it_logs_the_unmasked_verification_code_for_a_verification_template():
        client = DryRunEmailClient()
        template = cast(Any, Templates.CELESTIA_VERIFY_EMAIL)
        context = cast(EmailVerificationContext, EmailVerificationContextFactory.build())

        message = render_email_template(template, context).to_message("twilight@canterlot.com.br")

        with capture_logs() as logs:
            await client.send(message)

        debug_context = logs[0]["debug_context"]
        assert debug_context["code"] == context.code
        assert debug_context["action_url"] == str(context.action_url)

    async def it_logs_the_full_context_for_a_non_verification_template():
        client = DryRunEmailClient()
        template = cast(Any, Templates.CELESTIA_INVITE_INTERNAL)
        context = cast(InviteInternalContext, InviteInternalContextFactory.build())

        message = render_email_template(template, context).to_message("twilight@canterlot.com.br")

        with capture_logs() as logs:
            await client.send(message)

        debug_context = logs[0]["debug_context"]
        assert debug_context["inviter_name"] == context.inviter_name
        assert debug_context["club_name"] == context.club_name
        assert debug_context["action_url"] == str(context.action_url)
