from features.flags import load_flags


def home(request, render):
    """The home page, with the new dashboard for accounts in the beta"""
    flags = load_flags()
    template = "dashboard_v2.html" if flags.get("new_dashboard") else "dashboard.html"
    return render(template, user=request.user)
