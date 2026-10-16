from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import SearchForm
from .servers import ConfigurationError, load_servers
from .remote import SearchError, search_remote

@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    error = ""
    try:
        servers = load_servers()
    except ConfigurationError as exc:
        servers, error = [], str(exc)
    form = SearchForm(request.POST if request.method == "POST" else None, servers=servers)
    result = None
    selected = None
    if request.method == "POST" and servers and form.is_valid():
        selected = next(s for s in servers if s["id"] == form.cleaned_data["server"])
        try:
            result = search_remote(selected, form.cleaned_data)
        except SearchError as exc:
            error = str(exc)
    return render(request, "search/index.html", {
        "form": form, "servers": servers, "result": result, "error": error, "selected": selected,
        "server_scopes": {s["id"]: s["root"] for s in servers},
    })
