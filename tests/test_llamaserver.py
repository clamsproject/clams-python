"""
Tests for the llama-server backend (``clams.backends.llamaserver``) and
``ClamsGGUFPromptableApp``. A fake ``llama-server`` (a small python
HTTP server with the same command line and endpoints) stands in for
llama.cpp, so no binary, GPU or network is needed.
"""
import contextlib
import json
import os
import shutil
import stat
import sys
import tempfile
import textwrap
import unittest

import numpy as np
from PIL import Image

from clams.app import ClamsGGUFPromptableApp
from clams.backends import llamaserver

from tests.test_promptable import make_metadata

FAKE_SERVER = textwrap.dedent('''\
    #!{python}
    """Fake llama-server: /health, and a chat endpoint that echoes."""
    import argparse
    import json
    import os
    import sys
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    if os.environ.get('FAKE_LLAMA_EXIT'):
        print('error: failed to load model', flush=True)
        sys.exit(int(os.environ['FAKE_LLAMA_EXIT']))
    parser = argparse.ArgumentParser()
    parser.add_argument('--host')
    parser.add_argument('--port', type=int)
    args, _ = parser.parse_known_args()
    argv = sys.argv[1:]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                self._send({{'status': 'ok'}})
            elif self.path == '/props':
                # as llama-server: the command line, else the
                # LLAMA_ARG_* environment, else the built-in default
                # (the "model's trained context", one slot)
                def setting(flag, env, default):
                    if flag in argv:
                        return int(argv[argv.index(flag) + 1])
                    return int(os.environ.get(env, default))
                total = setting('--ctx-size', 'LLAMA_ARG_CTX_SIZE', 32768)
                slots = setting('--parallel', 'LLAMA_ARG_N_PARALLEL', 1)
                self._send({{'default_generation_settings': {{
                    'n_ctx': total // slots}}, 'total_slots': slots}})
            else:
                self.send_error(404)

        def do_POST(self):
            length = int(self.headers['Content-Length'])
            request = json.loads(self.rfile.read(length))
            messages = request.pop('messages')
            images = sum(
                1 for m in messages if isinstance(m['content'], list)
                for p in m['content'] if p['type'] == 'image_url')
            last_user = [m for m in messages if m['role'] == 'user'][-1]
            content = last_user['content']
            if isinstance(content, list):
                content = ' '.join(
                    p['text'] for p in content if p['type'] == 'text')
            if content == 'TOO_LONG':
                self._send({{'error': {{
                    'code': 400, 'type': 'exceed_context_size_error',
                    'message': 'request exceeds the available context'}}}},
                    status=400)
                return
            echo ={{'images': images, 'last_user': content,
                    'roles': [m['role'] for m in messages],
                    'assistant': [m['content'] for m in messages
                                  if m['role'] == 'assistant'],
                    'params': request, 'argv': argv,
                    'env': sorted(k for k in os.environ
                                  if k.startswith('LLAMA_ARG_'))}}
            self._send({{'choices': [
                {{'message': {{'role': 'assistant',
                              'content': json.dumps(echo)}}}}]}})

    print('server is listening', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
''')


@contextlib.contextmanager
def _environ(values):
    """Set environment variables for the block, then restore them."""
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                del os.environ[k]
            else:
                os.environ[k] = v


class FakeServerMixin:

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.fake_binary = os.path.join(cls.tmp, 'llama-server')
        with open(cls.fake_binary, 'w') as f:
            f.write(FAKE_SERVER.format(python=sys.executable))
        os.chmod(cls.fake_binary, os.stat(cls.fake_binary).st_mode
                 | stat.S_IXUSR)
        cls.model_file = os.path.join(cls.tmp, 'model-Q8_0.gguf')
        cls.mmproj_file = os.path.join(cls.tmp, 'mmproj-model-f16.gguf')
        for path in (cls.model_file, cls.mmproj_file):
            with open(path, 'wb') as f:
                f.write(b'GGUF')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestPickGGUFFiles(unittest.TestCase):

    FILES = ['README.md', 'model-Q4_K_M.gguf', 'model-Q8_0.gguf',
             'mmproj-model-f16.gguf']

    def test_variant_picks_model_and_mmproj(self):
        self.assertEqual(
            llamaserver._pick_gguf_files(self.FILES, 'q8_0'),
            (['model-Q8_0.gguf'], 'mmproj-model-f16.gguf'))

    def test_no_projector_gives_none(self):
        self.assertEqual(
            llamaserver._pick_gguf_files(['m-Q8_0.gguf'], 'Q8_0'),
            (['m-Q8_0.gguf'], None))

    def test_shards_are_returned_in_order(self):
        files = ['Q4_K_M/m-Q4_K_M-00002-of-00002.gguf',
                 'Q4_K_M/m-Q4_K_M-00001-of-00002.gguf']
        models, _ = llamaserver._pick_gguf_files(files, 'Q4_K_M')
        self.assertEqual(models, sorted(files))

    def test_missing_shard_is_ambiguous(self):
        files = ['m-Q4_K_M-00001-of-00003.gguf',
                 'm-Q4_K_M-00002-of-00003.gguf']
        with self.assertRaises(ValueError):
            llamaserver._pick_gguf_files(files, 'Q4_K_M')

    def test_unmatched_variant_raises(self):
        with self.assertRaisesRegex(ValueError, 'no GGUF model file'):
            llamaserver._pick_gguf_files(self.FILES, 'Q6_K')

    def test_ambiguous_variant_raises(self):
        with self.assertRaisesRegex(ValueError, 'several GGUF files'):
            llamaserver._pick_gguf_files(self.FILES, '')

    def test_several_projectors_raise(self):
        files = ['m-Q8_0.gguf', 'mmproj-f16.gguf', 'mmproj-f32.gguf']
        with self.assertRaisesRegex(ValueError, 'several mmproj'):
            llamaserver._pick_gguf_files(files, 'Q8_0')

    def test_draft_models_are_skipped_and_projector_matches_variant(self):
        # file listing of ggml-org/gemma-4-26B-A4B-it-GGUF
        files = ['dflash-gemma-4-26B-A4B-it-BF16.gguf',
                 'dflash-gemma-4-26B-A4B-it-Q8_0.gguf',
                 'gemma-4-26B-A4B-it-BF16.gguf',
                 'gemma-4-26B-A4B-it-Q4_0.gguf',
                 'gemma-4-26B-A4B-it-Q8_0.gguf',
                 'mmproj-gemma-4-26B-A4B-it-BF16.gguf',
                 'mmproj-gemma-4-26B-A4B-it-Q8_0.gguf',
                 'mtp-gemma-4-26B-A4B-it-BF16.gguf',
                 'mtp-gemma-4-26B-A4B-it-Q4_0.gguf',
                 'mtp-gemma-4-26B-A4B-it-Q8_0.gguf']
        self.assertEqual(
            llamaserver._pick_gguf_files(files, 'Q8_0'),
            (['gemma-4-26B-A4B-it-Q8_0.gguf'],
             'mmproj-gemma-4-26B-A4B-it-Q8_0.gguf'))
        # no Q4_0 projector: several remain, so the choice is ambiguous
        with self.assertRaisesRegex(ValueError, 'several mmproj'):
            llamaserver._pick_gguf_files(files, 'Q4_0')


class TestMessageConversion(unittest.TestCase):

    def test_pil_and_numpy_images_become_data_urls(self):
        pil = Image.new('RGB', (4, 4))
        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        for image in (pil, arr):
            url = llamaserver._image_to_data_url(image)
            self.assertTrue(url.startswith('data:image/png;base64,'))

    def test_urls_pass_through(self):
        url = 'https://example.com/frame.png'
        self.assertEqual(llamaserver._image_to_data_url(url), url)

    def test_image_parts_become_image_url_parts(self):
        conversation = [
            {'role': 'system', 'content': 'be brief'},
            {'role': 'user', 'content': [
                {'type': 'image', 'image': Image.new('RGB', (2, 2))},
                {'type': 'text', 'text': 'describe'}]},
        ]
        messages = llamaserver.to_openai_messages(conversation)
        self.assertEqual(messages[0], conversation[0])
        parts = messages[1]['content']
        self.assertEqual(parts[0]['type'], 'image_url')
        self.assertEqual(parts[1], {'type': 'text', 'text': 'describe'})

    def test_audio_parts_raise(self):
        conversation = [{'role': 'user', 'content': [
            {'type': 'audio', 'audio': b''}]}]
        with self.assertRaises(ValueError):
            llamaserver.to_openai_messages(conversation)


class TestLlamaServer(FakeServerMixin, unittest.TestCase):

    def make_server(self, **kwargs):
        kwargs.setdefault('binary', self.fake_binary)
        kwargs.setdefault('startup_timeout', 30)
        return llamaserver.LlamaServer(self.model_file, **kwargs)

    def test_command_line(self):
        server = self.make_server(mmproj_path=self.mmproj_file, port=1234)
        cmd = server._command()
        self.assertEqual(cmd[0], self.fake_binary)
        for flag, value in (('--model', self.model_file),
                            ('--mmproj', self.mmproj_file),
                            ('--port', '1234'),
                            ('--reasoning-format', 'none')):
            self.assertEqual(cmd[cmd.index(flag) + 1], value)
        # other settings go through the environment
        for flag in ('--ctx-size', '--parallel', '--n-gpu-layers',
                     '--ubatch-size'):
            self.assertNotIn(flag, cmd)

    def test_start_chat_stop(self):
        with self.make_server() as server:
            self.assertTrue(server.is_running())
            self.assertEqual(server.host, '127.0.0.1')
            reply = json.loads(server.chat(
                [{'role': 'user', 'content': 'hello'}], max_tokens=5))
            self.assertEqual(reply['last_user'], 'hello')
            self.assertEqual(reply['params'], {'max_tokens': 5})
            # the server's own defaults are read back
            self.assertEqual(server.slot_context, 32768)
            self.assertEqual(server.slots, 1)
        self.assertFalse(server.is_running())

    def test_environment_overrides_reach_the_server(self):
        # llama.cpp's own variables pass through; the two naming the
        # address do not, since the command line sets it
        env = {'LLAMA_ARG_CTX_SIZE': '8192', 'LLAMA_ARG_N_PARALLEL': '2',
               'LLAMA_ARG_HOST': '0.0.0.0', 'LLAMA_ARG_PORT': '8080'}
        with _environ(env):
            with self.make_server() as server:
                self.assertEqual(server.slot_context, 4096)
                self.assertEqual(server.slots, 2)
                reply = json.loads(server.chat(
                    [{'role': 'user', 'content': 'hello'}]))
                self.assertEqual(reply['env'], ['LLAMA_ARG_CTX_SIZE',
                                                'LLAMA_ARG_N_PARALLEL'])

    def test_llama_args_are_defaults_under_the_environment(self):
        llama_args = {'LLAMA_ARG_CTX_SIZE': 8192, 'LLAMA_ARG_UBATCH': 2048}
        with self.make_server(llama_args=llama_args) as server:
            self.assertEqual(server.slot_context, 8192)
            reply = json.loads(server.chat(
                [{'role': 'user', 'content': 'hello'}]))
            self.assertEqual(reply['env'], ['LLAMA_ARG_CTX_SIZE',
                                            'LLAMA_ARG_UBATCH'])
        # the environment of the app process wins over the defaults
        with _environ({'LLAMA_ARG_CTX_SIZE': '4096'}):
            server = self.make_server(llama_args=llama_args)
            env, settings = server._environment()
            self.assertEqual(env['LLAMA_ARG_CTX_SIZE'], '4096')
            self.assertEqual(env['LLAMA_ARG_UBATCH'], '2048')
            self.assertIn('LLAMA_ARG_CTX_SIZE=4096 (environment)', settings)
            self.assertIn('LLAMA_ARG_UBATCH=2048 (app)', settings)
            with server:
                self.assertEqual(server.slot_context, 4096)

    def test_llama_args_take_only_llama_arg_variables(self):
        for key in ('UBATCH', 'LLAMA_ARG_PORT', 'HF_TOKEN'):
            with self.assertRaisesRegex(ValueError, 'LLAMA_ARG_'):
                self.make_server(llama_args={key: '1'})

    def test_startup_failure_reports_server_output(self):
        os.environ['FAKE_LLAMA_EXIT'] = '3'
        try:
            with self.assertRaisesRegex(RuntimeError, 'failed to load'):
                self.make_server().start()
        finally:
            del os.environ['FAKE_LLAMA_EXIT']

    def test_only_owner_process_stops_server(self):
        server = self.make_server().start()
        try:
            owner = server._owner_pid
            server._owner_pid = owner + 1  # as seen from a forked child
            self.assertFalse(server.owned_here())
            server.stop()
            self.assertTrue(server.is_running())
            server._owner_pid = owner
        finally:
            server.stop()
        self.assertFalse(server.is_running())

    def test_forked_child_sees_parents_server_running(self):
        # a gunicorn worker cannot wait on the master's child process;
        # it must still see the server as running
        import warnings
        server = self.make_server().start()
        try:
            with warnings.catch_warnings():
                # the child only sends one health request, then exits
                warnings.filterwarnings('ignore', message='.*use of fork',
                                        category=DeprecationWarning)
                pid = os.fork()
            if pid == 0:  # child
                os._exit(0 if server.is_running() else 1)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        finally:
            server.stop()

    def test_log_levels_of_server_output(self):
        import logging
        level = llamaserver._log_level
        self.assertEqual(level('E load_backend: failed to load x.so'),
                         logging.WARNING)
        self.assertEqual(level('common_fit_params: warning: low memory'),
                         logging.WARNING)
        # the server's own log lines carry a timestamp before the level
        self.assertEqual(level('0.12.315.223 W srv load_model: cap '
                               'image_max_tokens (original=1120) to 512'),
                         logging.WARNING)
        self.assertEqual(level('slot print_timing: id 0 | prompt eval'),
                         logging.INFO)
        self.assertEqual(level('load_tensors: offloaded 49/49 layers to GPU'),
                         logging.INFO)
        self.assertEqual(level('load_tensors: CPU_Mapped model buffer size'),
                         logging.DEBUG)

    def test_missing_binary_raises(self):
        server = self.make_server(binary='no-such-llama-server-binary')
        with self.assertRaises(FileNotFoundError):
            server._command()

    def test_sigterm_stops_server(self):
        script = textwrap.dedent(f'''\
            import sys, time
            sys.path.insert(0, {os.getcwd()!r})
            from clams.backends.llamaserver import LlamaServer
            server = LlamaServer({self.model_file!r},
                                 binary={self.fake_binary!r},
                                 startup_timeout=30).start()
            print(server._process.pid, flush=True)
            time.sleep(60)
            ''')
        import signal
        import subprocess
        import time
        app = subprocess.Popen([sys.executable, '-c', script],
                               stdout=subprocess.PIPE, text=True)
        server_pid = int(app.stdout.readline())
        app.send_signal(signal.SIGTERM)
        app.wait(timeout=30)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                os.kill(server_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.2)
        else:
            os.kill(server_pid, signal.SIGKILL)
            self.fail('llama-server outlived its SIGTERMed parent')


class TestGGUFPromptableApp(FakeServerMixin, unittest.TestCase):

    SINGLETON_AV = {'org/fake-GGUF:Q8_0': 'abc1234'}
    MULTI_AV = {'org/fake-GGUF:Q8_0': 'abc1234',
                'org/other-GGUF:Q4_K_M': 'def5678'}

    def setUp(self):
        self._env = os.environ.get(llamaserver.LLAMA_SERVER_ENV)
        os.environ[llamaserver.LLAMA_SERVER_ENV] = self.fake_binary
        self._download = llamaserver.download_gguf
        self.downloads = []

        def fake_download(repo_id, revision, model_files, mmproj_file=None):
            self.downloads.append((repo_id, revision, list(model_files),
                                   mmproj_file))
            return ([self.model_file],
                    self.mmproj_file if mmproj_file else None)

        llamaserver.download_gguf = fake_download
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            if app.server is not None:
                app.server.stop()
        llamaserver.download_gguf = self._download
        if self._env is None:
            del os.environ[llamaserver.LLAMA_SERVER_ENV]
        else:
            os.environ[llamaserver.LLAMA_SERVER_ENV] = self._env

    def make_app(self, analyzer_versions=None, **attrs):
        analyzer_versions = analyzer_versions or self.SINGLETON_AV

        def load_metadata(_self):
            metadata = make_metadata(
                call_helper=False,
                analyzer_versions=dict(analyzer_versions))
            ClamsGGUFPromptableApp.inject_promptable_parameters(metadata)
            return metadata

        class_attrs = {
            '_load_appmetadata': load_metadata,
            '_appmetadata': lambda _self: None,
            '_annotate': lambda _self, mmif, **kw: mmif,
            'MODEL_FILES': {
                key: {'model': 'model-Q8_0.gguf',
                      'mmproj': 'mmproj-model-f16.gguf'}
                for key in analyzer_versions},
        }
        class_attrs.update(attrs)
        cls = type('TestGGUFApp', (ClamsGGUFPromptableApp,), class_attrs)
        app = cls()
        self.apps.append(app)
        return app

    def test_singleton_starts_server_at_init(self):
        app = self.make_app()
        self.assertTrue(app.server.is_running())
        self.assertEqual(app.loaded_model, ('org/fake-GGUF:Q8_0', 'abc1234'))
        self.assertEqual(self.downloads, [
            ('org/fake-GGUF', 'abc1234', ['model-Q8_0.gguf'],
             'mmproj-model-f16.gguf')])

    def test_multimember_family_starts_on_first_use_and_switches(self):
        app = self.make_app(self.MULTI_AV)
        self.assertIsNone(app.server)
        first = app.load_model('org/fake-GGUF:Q8_0')
        self.assertIs(app.load_model('org/fake-GGUF:Q8_0@abc1234'), first)
        second = app.load_model('org/other-GGUF:Q4_K_M')
        self.assertFalse(first.is_running())
        self.assertTrue(second.is_running())
        self.assertEqual(self.downloads[-1][:2],
                         ('org/other-GGUF', 'def5678'))

    def test_refine_params_pins_revision(self):
        app = self.make_app()
        refined = app._refine_params(prompt=['hi'])
        self.assertEqual(refined['model'], 'org/fake-GGUF:Q8_0@abc1234')

    def test_missing_model_parameter_raises(self):
        def load_metadata(_self):
            return make_metadata(call_helper=True,
                                 analyzer_versions=dict(self.SINGLETON_AV))

        cls = type('TestGGUFAppBad', (ClamsGGUFPromptableApp,), {
            '_load_appmetadata': load_metadata,
            '_appmetadata': lambda _self: None,
            '_annotate': lambda _self, mmif, **kw: mmif,
        })
        with self.assertRaisesRegex(ValueError, 'inject_promptable'):
            cls()

    def test_generate_keeps_order_and_maps_params(self):
        app = self.make_app(LLAMA_ARGS={'LLAMA_ARG_UBATCH': '2048'})
        images = [[Image.new('RGB', (4, 4))],
                  [Image.new('RGB', (4, 4)), Image.new('RGB', (4, 4))],
                  [Image.new('RGB', (4, 4))]]
        outputs = [json.loads(o) for o in app.generate(
            ['describe'], system_prompt='be brief', images=images,
            max_new_tokens=64, temperature=0.0, top_p=0.9, top_k=20,
            use_reasoning=True)]
        self.assertEqual([o['images'] for o in outputs], [1, 2, 1])
        self.assertEqual(outputs[0]['roles'], ['system', 'user'])
        self.assertEqual(outputs[0]['params'], {
            'max_tokens': 64, 'temperature': 0.0, 'top_p': 0.9,
            'top_k': 20, 'cache_prompt': False,
            'chat_template_kwargs': {'enable_thinking': True}})
        self.assertEqual(outputs[0]['env'], ['LLAMA_ARG_UBATCH'])

    def test_reasoning_is_off_unless_requested(self):
        app = self.make_app()
        output = json.loads(app.generate(['hi'])[0])
        self.assertEqual(output['params']['chat_template_kwargs'],
                         {'enable_thinking': False})

    def test_template_kwargs_override_is_sent(self):
        def template_kwargs(_self, **params):
            return {'reasoning_effort': 'low'}

        app = self.make_app(build_template_kwargs=template_kwargs)
        output = json.loads(app.generate(['hi'], use_reasoning=True)[0])
        self.assertEqual(output['params']['chat_template_kwargs'],
                         {'reasoning_effort': 'low'})

    def test_production_settings_keep_the_server(self):
        app = self.make_app()
        self.assertEqual(app.RESTIFIER_PRODUCTION_WORKERS, 1)
        self.assertEqual(app.RESTIFIER_PRODUCTION_MAX_REQUESTS, 0)

    def test_no_parallel_prompts_parameter(self):
        app = self.make_app()
        names = {p.name for p in app.metadata.parameters}
        self.assertNotIn('parallelPrompts', names)
        self.assertIn('maxImagesPerPrompt', names)
        with self.assertRaisesRegex(ValueError, 'LLAMA_ARG_N_PARALLEL'):
            app.generate_batched(['hi'], images=[[]], parallel_prompts=2)

    def test_batches_follow_the_server_slots(self):
        app = self.make_app(LLAMA_ARGS={'LLAMA_ARG_N_PARALLEL': '2'})
        self.assertEqual(app.server.slots, 2)
        progress = []
        app.report_progress = lambda done, total: progress.append(done)
        images = [[Image.new('RGB', (4, 4))] * k for k in (1, 2, 3)]
        outputs = [json.loads(o) for o in app.generate_batched(
            ['describe'], images=images)]
        self.assertEqual([o['images'] for o in outputs], [1, 2, 3])
        self.assertEqual(progress, [0, 2, 3])

    def test_text_only_prompt_runs_once(self):
        app = self.make_app()
        outputs = app.generate(['hello'])
        self.assertEqual(len(outputs), 1)
        self.assertEqual(json.loads(outputs[0])['last_user'], 'hello')

    def test_user_only_mode_fills_earlier_replies(self):
        app = self.make_app()
        output = json.loads(app.generate(
            ['first', 'second'], prompt_mode='user-only')[0])
        self.assertEqual(output['last_user'], 'second')
        self.assertEqual(output['roles'], ['user', 'assistant', 'user'])
        # the first reply was filled into the assistant placeholder
        self.assertEqual(json.loads(output['assistant'][0])['last_user'],
                         'first')

    def test_turn_taking_mode_sends_one_request(self):
        app = self.make_app()
        output = json.loads(app.generate(
            ['q1', 'a1', 'q2'], prompt_mode='turn-taking')[0])
        self.assertEqual(output['roles'], ['user', 'assistant', 'user'])
        self.assertEqual(output['assistant'], ['a1'])

    def test_audio_input_raises(self):
        app = self.make_app()
        with self.assertRaises(ValueError):
            app.generate(['hi'], audios=[[b'']])

    def test_generate_without_model_raises(self):
        app = self.make_app(self.MULTI_AV)
        with self.assertRaises(RuntimeError):
            app.generate(['hi'])

    def test_failed_prompt_yields_empty_string(self):
        app = self.make_app()
        app.server.stop()
        self.assertEqual(app.generate(['hi']), [''])

    def test_prompt_over_context_fails_the_request(self):
        app = self.make_app()
        with self.assertRaisesRegex(ValueError,
                                    r'\(32768 tokens\).*maxImagesPerPrompt'):
            app.generate(['TOO_LONG'])

    def test_server_of_another_process_is_not_replaced(self):
        app = self.make_app(self.MULTI_AV)
        server = app.load_model('org/fake-GGUF:Q8_0')
        owner = server._owner_pid
        server._owner_pid = owner + 1  # as seen from a gunicorn worker
        try:
            # the same model: used as it is
            self.assertIs(app.load_model('org/fake-GGUF:Q8_0'), server)
            # another model: cannot stop the other process's server
            with self.assertRaisesRegex(RuntimeError, 'another process'):
                app.load_model('org/other-GGUF:Q4_K_M')
            self.assertTrue(server.is_running())
        finally:
            server._owner_pid = owner


class TestOfflineResolve(unittest.TestCase):

    def test_cached_snapshot_is_listed_when_hub_is_unreachable(self):
        import huggingface_hub
        snapshot = tempfile.mkdtemp()
        for name in ('m-Q8_0-00001-of-00002.gguf',
                     'm-Q8_0-00002-of-00002.gguf', 'mmproj-m-f16.gguf'):
            open(os.path.join(snapshot, name), 'wb').close()
        originals = (huggingface_hub.HfApi.list_repo_files,
                     huggingface_hub.snapshot_download)

        def offline(*args, **kwargs):
            raise OSError('offline')

        huggingface_hub.HfApi.list_repo_files = offline
        huggingface_hub.snapshot_download = (
            lambda *a, **kw: snapshot if kw.get('local_files_only') else
            offline())
        try:
            self.assertEqual(
                llamaserver.resolve_gguf_files('org/m-GGUF', 'abc', 'Q8_0'),
                (['m-Q8_0-00001-of-00002.gguf', 'm-Q8_0-00002-of-00002.gguf'],
                 'mmproj-m-f16.gguf'))
        finally:
            (huggingface_hub.HfApi.list_repo_files,
             huggingface_hub.snapshot_download) = originals
            shutil.rmtree(snapshot, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
