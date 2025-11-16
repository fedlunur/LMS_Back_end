"""
Resend Email Service Utility
Provides a unified interface for sending emails via Resend API
"""
import logging
import os
from typing import Optional, List

from django.conf import settings
from django.template.loader import render_to_string
import resend

logger = logging.getLogger(__name__)

# Initialize Resend client - will be set from settings
def _get_resend_api_key():
    """Get Resend API key from settings"""
    return getattr(settings, "RESEND_API_KEY", os.getenv("RESEND_API_KEY", ""))


def send_email(
    subject: str,
    to_email: str,
    html_template: str,
    txt_template: Optional[str] = None,
    context: Optional[dict] = None,
    from_email: Optional[str] = None,
) -> bool:
    """
    Send an email using Resend API.
    
    Args:
        subject: Email subject line
        to_email: Recipient email address
        html_template: Path to HTML email template
        txt_template: Optional path to plain text email template
        context: Template context dictionary
        from_email: Sender email address (defaults to DEFAULT_FROM_EMAIL)
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    if context is None:
        context = {}
    
    from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    
    if not from_email:
        logger.error("No from_email specified and DEFAULT_FROM_EMAIL not set in settings")
        return False
    
    api_key = _get_resend_api_key()
    if not api_key:
        logger.error("RESEND_API_KEY not set in environment variables or settings")
        return False
    
    # Set API key for this request
    resend.api_key = api_key
    
    try:
        # Render HTML template
        html_body = render_to_string(html_template, context)
        
        # Render text template if provided, otherwise use HTML as fallback
        if txt_template:
            try:
                text_body = render_to_string(txt_template, context)
            except Exception:
                logger.debug(f"Plain-text template {txt_template} missing; using HTML as fallback")
                text_body = html_body
        else:
            text_body = html_body
        
        # Send email via Resend
        params = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        
        # Add text version if different from HTML
        if text_body != html_body:
            params["text"] = text_body
        
        email = resend.Emails.send(params)
        
        logger.info(f"Email sent successfully to {to_email} via Resend. Email ID: {email.get('id', 'unknown')}")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to send email to {to_email} via Resend: {str(e)}")
        return False

