def send_email(smtp, to, subject, body, reply_to=None):
    """Send a plain-text email, with a Reply-To address if there's one"""
    headers = f"To: {to}\nSubject: {subject}\n"
    if reply_to:
        headers += f"Reply-To: {reply_to}\n"
    smtp.sendmail("noreply@example.com", [to], f"{headers}\n{body}")
