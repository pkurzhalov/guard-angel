import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from ..config import settings

def get_greeting() -> str:
    """Determine the appropriate greeting based on the current time."""
    current_hour = datetime.now().hour
    return "Good morning" if current_hour < 12 else "Good afternoon"

def send_invoice_email(recipient_email: str, cc_list: list[str], subject: str, load_num: str, attachment_path: str):
    """Sends an email with the invoice attached."""
    
    msg = MIMEMultipart()
    msg["From"] = settings.smtp_user
    msg["To"] = recipient_email
    msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject

    body = (
        f"{get_greeting()}. Please see the attached invoice for load {load_num}.\n\n"
        "If you will be using a check for payment, "
        "please use the following address for mailing:\n\n"
        "9063 Caloosa Rd\n"
        "Fort Myers, FL 33967\n\n"
        "Please let me know if you need additional paperwork or have any questions.\n"
        "Thank you and have a good day!"
    )
    msg.attach(MIMEText(body, "plain"))

    with open(attachment_path, 'rb') as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(attachment_path)}")
        msg.attach(part)

    all_recipients = [recipient_email] + cc_list
    
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_user, all_recipients, msg.as_string())
    
    print(f"Invoice email sent to {all_recipients}")
