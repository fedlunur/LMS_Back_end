"""
Test script to verify Resend API integration
Run this with: python manage.py shell < lms_project/test_resend.py
Or: python -c "import django; django.setup(); from lms_project.test_resend import test_resend; test_resend()"
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_project.settings')
django.setup()

from django.conf import settings
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_resend():
    """Test Resend API connection and email sending"""
    print("=" * 50)
    print("Testing Resend API Integration")
    print("=" * 50)
    
    # Check API key
    api_key = getattr(settings, "RESEND_API_KEY", os.getenv("RESEND_API_KEY", ""))
    if not api_key:
        print("❌ ERROR: RESEND_API_KEY not found!")
        print("   Please set RESEND_API_KEY in your .env file or settings.py")
        return False
    else:
        print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    
    # Check from email
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not from_email:
        print("❌ ERROR: DEFAULT_FROM_EMAIL not set!")
        return False
    else:
        print(f"✅ From email: {from_email}")
    
    # Test Resend import
    try:
        import resend
        print(f"✅ Resend package imported successfully (version: {getattr(resend, '__version__', 'unknown')})")
    except ImportError as e:
        print(f"❌ ERROR: Failed to import resend: {e}")
        print("   Install with: pip install resend")
        return False
    
    # Test API call
    try:
        resend.api_key = api_key
        
        # Send a test email
        test_params = {
            "from": from_email,
            "to": ["delivered@resend.dev"],  # Resend test email
            "subject": "Test Email from LMS",
            "html": "<h1>Test Email</h1><p>This is a test email from your LMS system.</p>",
            "text": "Test Email\n\nThis is a test email from your LMS system."
        }
        
        print("\n📧 Attempting to send test email...")
        print(f"   From: {test_params['from']}")
        print(f"   To: {test_params['to']}")
        print(f"   Subject: {test_params['subject']}")
        
        response = resend.Emails.send(test_params)
        
        print(f"\n📬 Response received: {response}")
        print(f"   Response type: {type(response)}")
        
        if response:
            if isinstance(response, dict):
                email_id = response.get('id') or (response.get('data', {}) or {}).get('id')
                if email_id:
                    print(f"✅ SUCCESS! Email sent with ID: {email_id}")
                    return True
                else:
                    error = response.get('error') or (response.get('data', {}) or {}).get('error')
                    if error:
                        print(f"❌ ERROR: {error}")
                        return False
                    else:
                        print(f"⚠️  WARNING: Response received but no email ID found: {response}")
                        return False
            else:
                print(f"✅ SUCCESS! Email sent (response: {response})")
                return True
        else:
            print("❌ ERROR: No response from Resend API")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_resend()

