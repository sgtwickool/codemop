def build_message(subject, body, recipients=None):
    """A message for `recipients`, always copying in the on-call address"""
    recipients = list(recipients) if recipients is not None else []
    recipients.append("oncall@example.com")
    return {"subject": subject, "body": body, "to": recipients}
