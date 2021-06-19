from typing import Dict

from flask import Flask, request, Response
from flask_restful import Resource, Api

from clams.app import ClamsApp

from mmif import Mmif


class Restifier(object):
    """
    Resitifier is a simple wrapper that takes a :class:`.ClamsApp` object and
    turn it into a flaks-based HTTP server. For mapping between Python API and
    HTTP API, it relies on :class:`.ClamsHTTPApi` class.

    Constructor takes a :class:`.ClamsApp` instance and some options for flask configuration.

    :param app_instance: A :class:`.ClamsApp` to wrap.
    :param loopback: when True, the flask wrapper only listens to requests from localhost (used for debugging).
    :param port: Port number for the flask app to listen (used for debugging).
    :param debug: When True, the flask wrapper will run in `debug mode <https://flask.palletsprojects.com/en/1.1.x/quickstart/#debug-mode>`_.
    """
    def __init__(self, app_instance: ClamsApp, loopback: bool = False, port: int = 5000, debug: bool = True) -> None:
        super().__init__()
        self.cla = app_instance
        self.import_name = app_instance.__class__.__name__
        self.flask_app = Flask(self.import_name)
        self.host = 'localhost' if loopback else '0.0.0.0'
        self.port = port
        self.debug = debug
        api = Api(self.flask_app)
        api.add_resource(ClamsHTTPApi, '/',
                         resource_class_args=[self.cla])
    
    def run(self, **options):
        """
        Starts a development server. See :meth:`serve_development`.
        
        :param options: any additional options to pass to the web server.
        """
        self.serve_development(**options)
        
    def serve_production(self, **options):
        """
        Runs the CLAMS app as a flask webapp, using a production-ready web server (gunicorn, https://docs.gunicorn.org/en/stable/#).
        
        :param options: any additional options to pass to the web server.
        """
        import gunicorn.app.base
        import multiprocessing

        def number_of_workers():
            return (multiprocessing.cpu_count() * 2) + 1  # +1 to make sure at least two workers are running
        
        class ProductionApplication(gunicorn.app.base.BaseApplication):

            def __init__(self, app, host, port, **options):
                self.options = {
                    'bind': f'{host}:{port}',
                    'workers': number_of_workers(),
                    'threads': 2,
                }
                self.options.update(options)
                self.application = app
                super().__init__()

            def load_config(self):
                config = {key: value for key, value in self.options.items()
                          if key in self.cfg.settings and value is not None}
                for key, value in config.items():
                    self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        ProductionApplication(self.flask_app, self.host, self.port, **options).run()

    def serve_development(self, **options):
        """
        Runs the CLAMS app as a flask webapp, using flask built-in development server (https://werkzeug.palletsprojects.com/en/2.0.x/).
        
        :param options: any additional options to pass to the web server.
        """
        self.flask_app.run(host=self.host,
                           port=self.port,
                           debug=self.debug, 
                           **options)

    def test_client(self):
        """
        Returns `flask test client <https://flask.palletsprojects.com/en/1.1.x/testing/>`_.
        """
        return self.flask_app.test_client()


class ClamsHTTPApi(Resource):
    """
    ClamsHTTPApi provides mapping from HTTP verbs to Python API defined in :class:`.ClamsApp`.

    Constructor takes an instance of :class:`.ClamsApp`.
    """
    def __init__(self, cla_instance: ClamsApp):
        super().__init__()
        self.cla = cla_instance
        self.metadata_param_caster = ParameterCaster(self.cla.metadata_param_spec)
        self.annotate_param_caster = ParameterCaster(self.cla.annotate_param_spec)

    @staticmethod
    def json_to_response(json_str: str, status=200) -> Response:
        """
        Helper method to convert JSON output from a ClamsApp to a HTTP response.

        :param json_str: a serialized JSON .
        :param status: a numerical HTTP code to respond.
        :return: A HTTP response ready to send.
        """
        if not isinstance(json_str, str):
            json_str = str(json_str)
        return Response(response=json_str, status=status, mimetype='application/json')

    def get(self) -> Response:
        """
        Maps HTTP GET verb to :func:`~clams.app.ClamsApp.appmetadata`.

        :return: Returns app metadata in a HTTP response.
        """
        return self.json_to_response(self.cla.appmetadata(**self.metadata_param_caster.cast(request.args)))

    def post(self) -> Response:
        """
        Maps HTTP POST verb to :func:`~clams.app.ClamsApp.annotate`.
        Note that for now HTTP PUT verbs is also mapped to :func:`~clams.app.ClamsApp.annotate`.

        :return: Returns MMIF output from a ClamsApp in a HTTP response.
        """
        in_mmif = Mmif(request.get_data())
        params = self.annotate_param_caster.cast(request.args)
        try:
            return self.json_to_response(self.cla.annotate(in_mmif, **params))
        except Exception as e:
            return self.json_to_response(self.cla.record_error(in_mmif, params).serialize(pretty=True), status=500)

    put = post


class ParameterCaster(object):
    """
    A helper class to convert parameters passed by HTTP query strings to
    proper python data types.

    :param param_spec: A specification of a data types of parameters
    """
    def __init__(self, param_spec: Dict):
        self.param_spec = param_spec

    def cast(self, args):
        """
        Given parameter specification, tries to cast values of args to specified Python data types.

        :param args: k-v pairs
        :return: A new dictionary of type-casted args
        """
        casted = {}
        for k, v in args.items():
            if k in self.param_spec:
                if self.param_spec[k] == bool:
                    casted[k] = self.bool_param(v)
            else:
                casted[k] = v
        return casted

    @staticmethod
    def bool_param(value):
        """
        Helper function to convert string values to bool type.
        """
        return False if value in (False, 0, 'False', 'false', '0') else True
