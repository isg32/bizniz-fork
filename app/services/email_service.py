import resend
from jinja2 import Environment, FileSystemLoader
from app.core.config import settings

# --- Initialize Clients ---
try:
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")
    
    resend_client = resend.Resend(api_key=settings.RESEND_API_KEY)
    
    template_loader = FileSystemLoader(searchpath="app/templates/emails")
    template_env = Environment(loader=template_loader)
    
    print("Resend and Email Template clients initialized successfully.")

except Exception as e:
    resend_client = None
    print(f"WARNING: Could not initialize Resend client. Emails will not be sent. Error: {e}")


# --- Core Email Sending Function ---

def _send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Internal helper function to send an email using Resend."""
    if not resend_client:
        print(f"EMAIL-FAIL: Resend client not available. Cannot send email to {to_email}.")
        return False
    
    try:
        params = {
            "from": f"{settings.PROJECT_NAME} <noreply@updates.bugswriter.com>", # IMPORTANT: Change to your verified Resend domain
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
        email = resend_client.emails.send(params)
        print(f"EMAIL-SUCCESS: Successfully sent '{subject}' email to {to_email}. Message ID: {email['id']}")
        return True
    except Exception as e:
        print(f"EMAIL-FAIL: Failed to send '{subject}' email to {to_email}. Error: {e}")
        return False

# --- Public Functions for Specific Emails ---

def send_renewal_receipt_email(to_email: str, user_name: str, coins_added: int, plan_name: str) -> bool:
    """Renders and sends a receipt for a successful subscription renewal."""
    subject = f"Your {settings.PROJECT_NAME} Subscription Renewal"
    template = template_env.get_template("renewal_receipt.html")
    html_content = template.render(
        user_name=user_name,
        coins_added=coins_added,
        plan_name=plan_name,
        project_name=settings.PROJECT_NAME,
        coins_name_plural=settings.CREDIT_UNIT_NAME_PLURAL
    )
    return _send_email(to_email, subject, html_content)