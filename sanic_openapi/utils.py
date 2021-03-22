import re

from sanic.views import CompositionView


def get_uri_filter(app):
    """
    Return a filter function that takes a URI and returns whether it should
    be filter out from the swagger documentation or not.

    Arguments:
        app: The application to take `config.API_URI_FILTER` from. Possible
             values for this config option are: `slash` (to keep URIs that
             end with a `/`), `all` (to keep all URIs). All other values
             default to keep all URIs that don't end with a `/`.

    Returns:
        `True` if the URI should be *filtered out* from the swagger
        documentation, and `False` if it should be kept in the documentation.
    """
    choice = getattr(app.config, "API_URI_FILTER", None)

    if choice == "slash":
        # Keep URIs that end with a /.
        return lambda uri: not uri.endswith("/")

    if choice == "all":
        # Keep all URIs.
        return lambda uri: False

    # Keep URIs that don't end with a /, (special case: "/").
    return lambda uri: len(uri) > 1 and uri.endswith("/")


def remove_nulls(dictionary, deep=True):
    """
    Removes all null values from a dictionary.
    """
    return {k: remove_nulls(v, deep) if deep and type(v) is dict else v for k, v in dictionary.items() if v is not None}


def remove_nulls_from_kwargs(**kwargs):
    return remove_nulls(kwargs, deep=False)


def get_blueprinted_routes(app):
    for blueprint in app.blueprints.values():
        if not hasattr(blueprint, "routes"):
            continue

        for route in blueprint.routes:
            if not hasattr(route, "handler"):
                # in sanic 21.3, "route" is now something different:
                #   an instance of sanic_routing.route.Route
                # can't typecheck because code needs to be compatible
                # with older sanic versions, but "handler" does not exist
                # on sanic>=21.3 route
                #
                # the good news - now class based views are already handled
                for method_handlers in route.handlers.values():
                    for handler in method_handlers.values():
                        if len(handler):
                            # handler is a list of functions
                            # can be size zero for some reason, not sure when
                            # that occurs ...
                            yield (blueprint.name, handler[0])
                continue

            if hasattr(route.handler, "view_class"):
                # before sanic 21.3, route.handler could be a number of
                # different things, so have to type check
                for http_method in route.methods:
                    _handler = getattr(route.handler.view_class, http_method.lower(), None)
                    if _handler:
                        yield (blueprint.name, _handler)
            else:
                yield (blueprint.name, route.handler)


def get_all_routes(app, skip_prefix):
    uri_filter = get_uri_filter(app)
    for uri, route in app.router.routes_all.items():

        if not hasattr(route, "handler"):
            # new sanic 21.3 style route...

            # prior to sanic 21.3 routes came in both forms 
            # (e.g. /test and /test/ )

            # after sanic 21.3 routes come in one form, with an attribute "strict"
            # so we simulate that ourselves:

            if route.strict:
                uris = ['/' + '/'.join(uri)]
            else:
                uris = ['/' + '/'.join(uri), '/' + '/'.join(uri) + '/']

            for uri in uris:
                if uri_filter(uri):
                    continue

                if route.raw_path.startswith(skip_prefix.lstrip('/')):
                    continue

                if route.name and "static" in route.name:
                    continue

                for parameter in route.params.values():
                    uri = re.sub("<" + parameter.name + ".*?>", "{" + parameter.name + "}", uri)

                for method_handlers in route.handlers.values():

                    # same check as before, to handle case when list is of size 1
                    method_handlers = {k: v[0] for k, v in method_handlers.items() if len(v)}

                    yield (uri, route.name, route.params.values(), method_handlers.items())

            continue

        # Ignore routes under swagger blueprint
        if route.uri.startswith(skip_prefix):
            continue

        # Apply the URI filter
        if uri_filter(uri):
            continue

        # route.name will be None when using class based view
        if route.name and "static" in route.name:
            continue

        # create dict httpMethod -> handler
        # e.g.  {"GET" -> lambda request: response}

        if type(route.handler) is CompositionView:
            method_handlers = route.handler.handlers

        elif hasattr(route.handler, "view_class"):
            method_handlers = {
                method: getattr(route.handler.view_class, method.lower())
                for method in route.methods}
        else:
            method_handlers = {method: route.handler
                               for method in route.methods}

        for parameter in route.parameters:
            uri = re.sub("<" + parameter.name + ".*?>", "{" + parameter.name + "}", uri)

        yield uri, route.name, route.parameters, method_handlers.items()
