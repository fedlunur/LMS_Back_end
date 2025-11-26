"""
Resend Email Service Utility
Provides a unified interface for sending emails via Resend API
Falls back to Django SMTP if Resend fails
"""
import logging
import os
from typing import Optional, List

from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

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
    
    try:
        # Import resend here to avoid import errors if not installed
        import resend
        
        # Set API key if not already set (should be set in settings.py, but this is a fallback)
        if not resend.api_key:
            resend.api_key = api_key
        
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
        
        # Prepare email parameters
        params = {
            "from": from_email,
            "to": [to_email] if isinstance(to_email, str) else to_email,
            "subject": subject,
            "html": html_body,
        }
        
        # Add text version if different from HTML
        if text_body != html_body:
            params["text"] = text_body
        
        # Send email via Resend API
        logger.info(f"Attempting to send email via Resend to {to_email} with subject: {subject}")
        logger.debug(f"Email params: from={from_email}, to={to_email}, subject={subject}")
        
        try:
            response = resend.Emails.send(params)
        except Exception as api_error:
            # Resend SDK might raise exceptions for API errors
            logger.error(f"Resend API raised an exception: {type(api_error).__name__}: {str(api_error)}")
            # Check if it's a specific Resend error
            if hasattr(api_error, 'status_code'):
                logger.error(f"HTTP Status Code: {api_error.status_code}")
            if hasattr(api_error, 'response'):
                logger.error(f"Error Response: {api_error.response}")
            raise  # Re-raise to be caught by outer exception handler
        
        # Log the full response for debugging
        logger.info(f"Resend API response received: {response} (type: {type(response)})")
        
        # Check response - Resend returns dict with 'id' on success
        # Response format can be: {'id': '...'} or {'data': {'id': '...'}} or just the id string
        if response:
            if isinstance(response, dict):
                email_id = response.get('id') or (response.get('data', {}) or {}).get('id', 'unknown')
                if email_id and email_id != 'unknown':
                    logger.info(f"Email sent successfully to {to_email} via Resend. Email ID: {email_id}")
                    return True
                else:
                    # Check if there's an error in the response
                    error = response.get('error') or (response.get('data', {}) or {}).get('error')
                    if error:
                        logger.error(f"Resend API returned an error: {error}")
                        return False
                    else:
                        logger.warning(f"Resend API response missing email ID: {response}")
                        # Still return True if we got a response without error
                        return True
            elif isinstance(response, str):
                # Sometimes Resend returns just the email ID as a string
                logger.info(f"Email sent successfully to {to_email} via Resend. Email ID: {response}")
                return True
            else:
                logger.warning(f"Unexpected response type from Resend API: {type(response)}, value: {response}")
                return False
        else:
            logger.error("Resend API returned None/empty response")
            return False
        
    except ImportError:
        logger.warning("Resend package not installed. Falling back to Django SMTP.")
        return _send_via_smtp(subject, to_email, html_template, txt_template, context, from_email)
    except Exception as e:
        # Check if it's a ResendError (domain not verified, etc.)
        error_type = type(e).__name__
        error_str = str(e).lower()
        
        # Try to import ResendError to check if this is a Resend-specific error
        try:
            from resend.exceptions import ResendError
            if isinstance(e, ResendError):
                logger.warning(f"Resend API error ({error_type}): {str(e)}. Falling back to Django SMTP.")
            else:
                logger.warning(f"Resend failed with error ({error_type}): {str(e)}. Falling back to Django SMTP.")
        except ImportError:
            # Can't import ResendError, check error message
            if 'domain' in error_str and 'not verified' in error_str:
                logger.warning(f"Resend domain not verified: {str(e)}. Falling back to Django SMTP.")
            elif 'resend' in error_type.lower():
                logger.warning(f"Resend API error: {str(e)}. Falling back to Django SMTP.")
            else:
                logger.warning(f"Resend failed with error: {str(e)}. Falling back to Django SMTP.")
        
        # Fallback to Django SMTP
        return _send_via_smtp(subject, to_email, html_template, txt_template, context, from_email)


def _send_via_smtp(
    subject: str,
    to_email: str,
    html_template: str,
    txt_template: Optional[str] = None,
    context: Optional[dict] = None,
    from_email: Optional[str] = None,
) -> bool:
    """
    Fallback method to send email using Django's SMTP backend.
    
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
    
    # Check if SMTP is configured
    email_host = getattr(settings, "EMAIL_HOST", "")
    if not email_host:
        logger.error("SMTP fallback not configured: EMAIL_HOST not set in settings")
        return False
    
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
        
        # Send email via Django SMTP
        logger.info(f"Sending email via Django SMTP to {to_email} with subject: {subject}")
        
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[to_email] if isinstance(to_email, str) else to_email,
        )
        email_message.attach_alternative(html_body, "text/html")
        email_message.send()
        
        logger.info(f"Email sent successfully to {to_email} via Django SMTP")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to send email to {to_email} via Django SMTP: {str(e)}")
        return False

