from flask import Flask, request
from flask_restful import Resource, Api

from clams import Mmif


class Restifier(object):
    def __init__(self, app_instance):
        super().__init__()
        self.cla = app_instance
        self.import_name = app_instance.__class__.__name__
        self.flask_app = Flask(self.import_name)
        # TODO setters for these flask params
        self.host = '0.0.0.0'
        self.port = 5000
        self.debug = True
        api = Api(self.flask_app)
        api.add_resource(ClamsRestfulApi, '/',
                         resource_class_args=[self.cla])

    def run(self):
        self.flask_app.run(host=self.host,
                           port=self.port,
                           debug=self.debug)

    def test_client(self):
        return self.flask_app.test_client()


class ClamsRestfulApi(Resource):

    def __init__(self, cla_instance):
        super().__init__()
        self.cla = cla_instance

    def get(self):
        return self.cla.appmetadata()

    def post(self):
        return str(self.cla.sniff(Mmif(request.get_data())))

    def put(self):
        return str(self.cla.annotate(Mmif(request.get_data())))

