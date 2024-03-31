import jsonschema
from flask import Flask, request, Response
from flask_restful import Resource, Api
from mmif import Mmif

from clams.app import ClamsApp


class Restifier(object):
    """
    Restifier is a simple wrapper that takes a :class:`.ClamsApp` object and
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
                    # because the default is 'None'
                    'accesslog': '-',
                    # errorlog, however, is redirected to stderr by default since 19.2, so no need to set
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
        Maps HTTP GET verb to :meth:`~clams.app.ClamsApp.appmetadata`.

        :return: Returns app metadata in a HTTP response.
        """
        return self.json_to_response(self.cla.appmetadata(**request.args))

    def post(self) -> Response:
        """
        Maps HTTP POST verb to :meth:`~clams.app.ClamsApp.annotate`.
        Note that for now HTTP PUT verbs is also mapped to :meth:`~clams.app.ClamsApp.annotate`.

        :return: Returns MMIF output from a ClamsApp in a HTTP response.
        """
        raw_data = request.get_data().decode('utf-8')
        # this will catch duplicate arguments with different values into a list under the key
        raw_params = request.args.to_dict(flat=False)
        try:
            _ = Mmif(raw_data)
        except jsonschema.exceptions.ValidationError as e:
            return Response(response="Invalid input data. See below for validation error.\n\n" + str(e), status=500, mimetype='text/plain')
        try:
            return self.json_to_response(self.cla.annotate(raw_data, **raw_params))
        except Exception:
            return self.json_to_response(self.cla.record_error(raw_data, **raw_params).serialize(pretty=True), status=500)

    put = post
