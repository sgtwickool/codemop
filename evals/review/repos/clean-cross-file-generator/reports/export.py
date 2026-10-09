import csv

from reports.users import active_users


def export_active_users(db, out):
    """Write every active user to a CSV file"""
    writer = csv.writer(out)
    writer.writerow(["id", "email", "last_login"])
    for user in active_users(db):
        writer.writerow([user["id"], user["email"], user["last_login"]])
