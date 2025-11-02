# app/services/internal/email_service.py

import resend
import logging
from jinja2 import Environment, FileSystemLoader
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Initialization ---
try:
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")

    resend.api_key = settings.RESEND_API_KEY

    # Setup Jinja2 to render email templates
    template_loader = FileSystemLoader(searchpath="app/templates/emails")
    template_env = Environment(loader=template_loader)

    logger.info("Resend and Email Template clients initialized successfully.")

except Exception as e:
    resend.api_key = None
    # This will be logged as a critical error, but we allow the app to start
    # so other parts can function. Emails will fail gracefully.
    logger.critical(
        f"EMAIL-SVC: Could not initialize Resend client. Emails will not be sent. Error: {e}"
    )


# --- Core Email Sending Function ---


def _send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Internal helper function to send an email using the Resend SDK."""
    if not resend.api_key:
        logger.error(
            f"EMAIL-SVC-FAIL: Resend client not available. Cannot send '{subject}' to {to_email}."
        )
        return False

    try:
        params: resend.Emails.SendParams = {
            "from": f"{settings.PROJECT_NAME} <noreply@updates.bugswriter.com>",
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }

        email = resend.Emails.send(params)

        logger.info(
            f"EMAIL-SVC-SUCCESS: Sent '{subject}' to {to_email}. Message ID: {email['id']}"
        )
        return True
    except Exception as e:
        logger.error(
            f"EMAIL-SVC-FAIL: Failed to send '{subject}' to {to_email}. Error: {e}",
            exc_info=True,
        )
        return False


# --- Public Functions for Specific Templated Emails ---


def send_renewal_receipt_email(
    to_email: str, user_name: str, coins_added: int, plan_name: str
) -> bool:
    """Renders and sends a receipt for a successful subscription renewal."""
    try:
        subject = f"Your {settings.PROJECT_NAME} Subscription Renewal"
        template = template_env.get_template("renewal_receipt.html")
        # Context for the Jinja2 template
        context = {
            "user_name": user_name,
            "coins_added": coins_added,
            "plan_name": plan_name,
            "project_name": settings.PROJECT_NAME,
            "coins_name_plural": settings.CREDIT_UNIT_NAME_PLURAL,
        }
        html_content = template.render(context)
        return _send_email(to_email, subject, html_content)
    except Exception as e:
        logger.error(
            f"EMAIL-SVC-TEMPLATE-FAIL: Failed to render renewal_receipt.html. Error: {e}",
            exc_info=True,
        )
        return False


def send_subscription_started_email(
    to_email: str, user_name: str, plan_name: str, dashboard_url: str
) -> bool:
    """
    Renders and sends an email confirming a new subscription.
    Now requires an explicit dashboard_url.
    """
    try:
        subject = f"Welcome to your {plan_name} plan!"
        template = template_env.get_template("subscription_started.html")
        context = {
            "user_name": user_name,
            "plan_name": plan_name,
            "project_name": settings.PROJECT_NAME,
            "dashboard_url": dashboard_url,  # Pass the URL for the button
        }
        html_content = template.render(context)
        return _send_email(to_email, subject, html_content)
    except Exception as e:
        logger.error(
            f"EMAIL-SVC-TEMPLATE-FAIL: Failed to render subscription_started.html. Error: {e}",
            exc_info=True,
        )
        return False


def send_subscription_cancelled_email(
    to_email: str, user_name: str, plan_name: str, portal_url: str
) -> bool:
    """
    Renders and sends an email confirming subscription cancellation.
    Now requires an explicit portal_url.
    """
    try:
        subject = f"Your {settings.PROJECT_NAME} subscription has been cancelled"
        template = template_env.get_template("subscription_cancelled.html")
        context = {
            "user_name": user_name,
            "plan_name": plan_name,
            "project_name": settings.PROJECT_NAME,
            "portal_url": portal_url,  # Pass the URL for the button
        }
        html_content = template.render(context)
        return _send_email(to_email, subject, html_content)
    except Exception as e:
        logger.error(
            f"EMAIL-SVC-TEMPLATE-FAIL: Failed to render subscription_cancelled.html. Error: {e}",
            exc_info=True,
        )
        return False


def send_notification_email(to_email: str, subject: str, message_html: str) -> bool:
    """Renders and sends a generic notification email for the internal API."""
    try:
        template = template_env.get_template("general_notification.html")
        context = {
            "subject": subject,
            "message_html": message_html,
            "project_name": settings.PROJECT_NAME,
        }
        html_content = template.render(context)
        return _send_email(to_email, subject, html_content)
    except Exception as e:
        logger.error(
            f"EMAIL-SVC-TEMPLATE-FAIL: Failed to render general_notification.html. Error: {e}",
            exc_info=True,
        )
        return False
