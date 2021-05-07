import inspect
from distutils.version import LooseVersion
from os.path import abspath, dirname, realpath

from sanic import __version__ as sanic_version
from sanic.blueprints import Blueprint
from sanic.response import json, redirect

from ..autodoc import YamlStyleParametersParser
from ..utils import get_all_routes, get_blueprinted_routes, remove_nulls
from .doc import RouteSpec, definitions, route_specs, serialize_schema
from .spec import Spec as Swagger2Spec

SANIC_VERSION = LooseVersion(sanic_version)
SANIC_21_3_0 = LooseVersion("21.3.0")


def blueprint_factory():
    swagger_blueprint = Blueprint("swagger", url_prefix="/swagger")

    dir_path = dirname(dirname(realpath(__file__)))
    dir_path = abspath(dir_path + "/ui")

    swagger_blueprint.static("/", dir_path + "/index.html", strict_slashes=True)
    swagger_blueprint.static("/", dir_path)

    # Redirect "/swagger" to "/swagger/"
    @swagger_blueprint.route("", strict_slashes=True)
    def index(request):
        return redirect("{}/".format(swagger_blueprint.url_prefix))

    @swagger_blueprint.route("/swagger.json")
    def spec(request):

        if SANIC_VERSION >= SANIC_21_3_0:
            return json(swagger_blueprint.ctx._spec.as_dict)
        else:
            return json(swagger_blueprint._spec.as_dict)

    @swagger_blueprint.route("/swagger-config")
    def config(request):
        return json(getattr(request.app.config, "SWAGGER_UI_CONFIGURATION", {}))

    @swagger_blueprint.listener("after_server_start")
    def build_spec(app, loop):
        # --------------------------------------------------------------- #
        # Blueprint Tags
        # --------------------------------------------------------------- #

        for blueprint_name, handler in get_blueprinted_routes(app):
            route_spec = route_specs[handler]
            route_spec.blueprint = blueprint_name
            if not route_spec.tags:
                route_spec.tags.append(blueprint_name)

        paths = {}

        for (uri, route_name, route_parameters, method_handlers) in get_all_routes(app, swagger_blueprint.url_prefix):

            # --------------------------------------------------------------- #
            # Methods
            # --------------------------------------------------------------- #

            methods = {}
            for _method, _handler in method_handlers:

                route_spec = route_specs.get(_handler) or RouteSpec()

                if route_spec.exclude:
                    continue

                api_consumes_content_types = getattr(app.config, "API_CONSUMES_CONTENT_TYPES", ["application/json"])
                consumes_content_types = route_spec.consumes_content_type or api_consumes_content_types

                api_produces_content_types = getattr(app.config, "API_PRODUCES_CONTENT_TYPES", ["application/json"])
                produces_content_types = route_spec.produces_content_type or api_produces_content_types

                # Parameters - Path & Query String
                route_parameters = []
                for parameter in route_parameters:
                    route_parameters.append(
                        {
                            **serialize_schema(parameter.cast),
                            "required": True,
                            "in": "path",
                            "name": parameter.name,
                        }
                    )

                for consumer in route_spec.consumes:
                    spec = serialize_schema(consumer.field)
                    if "properties" in spec:
                        for name, prop_spec in spec["properties"].items():
                            route_param = {
                                **prop_spec,
                                "required": consumer.required,
                                "in": consumer.location,
                                "name": name,
                            }
                    else:
                        route_param = {
                            **spec,
                            "required": consumer.required,
                            "in": consumer.location,
                            "name": consumer.field.name
                            if not isinstance(consumer.field, type) and hasattr(consumer.field, "name")
                            else "body",
                        }

                    if "$ref" in route_param:
                        route_param["schema"] = {"$ref": route_param["$ref"]}
                        del route_param["$ref"]

                    if route_param["in"] == "path":
                        route_param["required"] = True
                        for i, parameter in enumerate(route_parameters):
                            if parameter["name"] == route_param["name"]:
                                route_parameters.pop(i)
                                break

                    route_parameters.append(route_param)

                responses = {}

                for (status_code, routefield) in route_spec.response:
                    responses["{}".format(status_code)] = {
                        "schema": serialize_schema(routefield.field),
                        "description": routefield.description,
                    }

                if route_spec.produces:
                    responses["200"] = {
                        "schema": serialize_schema(route_spec.produces.field),
                        "description": route_spec.produces.description,
                    }
                elif not responses:
                    responses["200"] = {"description": "OK"}

                y = YamlStyleParametersParser(inspect.getdoc(_handler))
                autodoc_endpoint = y.to_openAPI_2()

                # if the user has manualy added a description or summary via
                # the decorator, then use theirs

                if route_spec.summary:
                    autodoc_endpoint["summary"] = route_spec.summary

                if route_spec.description:
                    autodoc_endpoint["description"] = route_spec.description

                endpoint = remove_nulls(
                    {
                        "operationId": route_spec.operation or route_name,
                        "summary": route_spec.summary,
                        "description": route_spec.description,
                        "consumes": consumes_content_types,
                        "produces": produces_content_types,
                        "tags": route_spec.tags or None,
                        "parameters": route_parameters,
                        "responses": responses,
                    }
                )

                # otherwise, update with anything parsed from the
                # docstrings yaml
                endpoint.update(autodoc_endpoint)

                methods[_method.lower()] = endpoint

            if methods:
                paths[uri] = methods

        # --------------------------------------------------------------- #
        # Definitions
        # --------------------------------------------------------------- #

        _spec = Swagger2Spec(app=app)

        _spec.add_definitions(definitions={obj.object_name: definition for obj, definition in definitions.values()})

        # --------------------------------------------------------------- #
        # Tags
        # --------------------------------------------------------------- #

        tags = set()
        for route_spec in route_specs.values():
            if route_spec.blueprint != "swagger":
                tags.update(route_spec.tags)

        _spec.add_tags(tags=[{"name": name} for name in tags])

        _spec.add_paths(paths)

        if SANIC_VERSION >= SANIC_21_3_0:
            swagger_blueprint.ctx._spec = _spec
        else:
            swagger_blueprint._spec = _spec

    return swagger_blueprint
