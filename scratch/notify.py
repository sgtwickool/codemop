def build_message(subject, body, recipients=[]):
    """A message for `recipients`, always copying in the on-call address"""
    recipients.append("oncall@example.com")
    return {"subject": subject, "body": body, "to": recipients}
