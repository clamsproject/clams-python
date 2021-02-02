from flask import Flask, request, Response
from flask_restful import Resource, Api

from mmif import Mmif


class Restifier(object):
    def __init__(self, app_instance, loopback=False, port=5000, debug=True):
        super().__init__()
        self.cla = app_instance
        self.import_name = app_instance.__class__.__name__
        self.flask_app = Flask(self.import_name)
        self.host = 'localhost' if loopback else '0.0.0.0'
        self.port = port
        self.debug = debug
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

    @staticmethod
    def json_to_response(json_str: str, status=200):
        if not isinstance(json_str, str):
            json_str = str(json_str)
        return Response(response=json_str, status=status, mimetype='application/json')

    def get(self) -> Response:
        return self.json_to_response(self.cla.appmetadata())

    def post(self) -> Response:
        try:
            return self.json_to_response(self.cla.annotate(Mmif(request.get_data()), **request.args))
        except TypeError as e:
            return Response(status=415, response=str(e))
        except FileNotFoundError as e:
            return Response(status=404, response=str(e))
        except Exception as e:
            return Response(status=400, response=str(e))

    put = post
