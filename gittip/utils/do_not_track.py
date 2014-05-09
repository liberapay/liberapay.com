def inbound(request):
    if request.line.uri.startswith('/assets/'): return

    # Implement Do Not Track universal opt-out
    DoNotTrackHeader = "DNT"
    DoNotTrackValue = "1"

    aspenHeader = DoNotTrackHeader.capitalize()

    if (aspenHeader in request.headers) and (request.headers[aspenHeader] == DoNotTrackValue):
        request.context['dnt'] = True
    else:
        request.context['dnt'] = False
