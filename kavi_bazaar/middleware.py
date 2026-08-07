class MediaCacheMiddleware:
    """Long browser cache for uploaded images so navigation is instant."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/images/') and response.status_code == 200:
            response['Cache-Control'] = 'public, max-age=604800, immutable'
        elif request.path.startswith('/dashboard/') and response.status_code == 200:
            response['Cache-Control'] = 'no-store, max-age=0'
        return response
