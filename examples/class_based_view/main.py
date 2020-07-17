from sanic_openapi import doc
from sanic_openapi import swagger_blueprint
from sanic import Sanic
from sanic.response import json

from blueprint import blueprint

app = Sanic()

app.blueprint(swagger_blueprint)
app.blueprint(blueprint)


@app.post("/plain", strict_slashes=True)
@doc.summary("Creates a user")
@doc.consumes({"user": {"name": str}}, location="body")
async def create_user(request):
    return json({})



@app.post("/update", strict_slashes=True)
@doc.summary("updates a user")
@doc.consumes({"user": {"name": doc.String(description="name", example="example_user")}}, location="body")
async def create_user(request):
    return json({})



app.config.API_VERSION = 'pre-alpha'
app.config.API_TITLE = 'Class Based View Demonstration API'
app.config.API_TERMS_OF_SERVICE = 'Use with caution!'
app.config.API_CONTACT_EMAIL = 'guoli-lyu@hotmail.com'

app.run(host="0.0.0.0", debug=True)
