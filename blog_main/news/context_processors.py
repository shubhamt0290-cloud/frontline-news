# added by shubham - values every template needs (footer contact email, phone + LinkedIn)
import re

from django.conf import settings


def site_info(request):
    phone = settings.CONTACT_PHONE
    return {
        'contact_email': settings.CONTACT_EMAIL,
        'contact_phone': phone,  # added by shubham - shown as e.g. "+91 98765 43210"
        'contact_phone_link': re.sub(r'[^\d+]', '', phone),  # added by shubham - e.g. "+919876543210" for tel: links
        'linkedin_url': settings.LINKEDIN_URL,  # added by shubham - LinkedIn profile link
    }
