import argparse
import json
import sys
from typing import Dict, List, Optional, Tuple, Union

from mmif import Mmif

from clams.appmetadata import map_param_kv_delimiter

ENVELOPE_KEY = 'parameters'
MMIF_KEY = 'mmif'


class EnvelopeError(ValueError):
    """
    Raised when an input body is detected as an envelope (has a
    ``"parameters"`` key) but is otherwise malformed. Subclasses
    ``ValueError`` so existing ``except ValueError`` handlers keep
    working, while still being distinguishable from unrelated
    ``ValueError``\\ s raised by app code.
    """


def normalize_params(params: dict) -> Dict[str, List[str]]:
    """
    Normalize JSON-native parameter values to the
    ``Dict[str, List[str]]`` format expected by
    :class:`~clams.app.ParameterCaster`.

    :param params: parameter dict with JSON-native values
    :returns: normalized dict where every value is a list of strings
    :rtype: Dict[str, List[str]]
    """
    normalized = {}
    for k, v in params.items():
        if isinstance(v, list):
            normalized[k] = [str(elem) for elem in v]
        elif isinstance(v, dict):
            normalized[k] = [
                f"{dk}{map_param_kv_delimiter}{dv}"
                for dk, dv in v.items()
            ]
        else:
            normalized[k] = [str(v)]
    return normalized


def is_envelope(body: dict) -> bool:
    """
    Check whether a parsed JSON body is an envelope.

    Detection relies on the presence of a top-level ``"parameters"``
    key, which is never part of the MMIF schema.

    :param body: parsed JSON dict
    :returns: True if the body appears to be an envelope
    :rtype: bool
    """
    return isinstance(body, dict) and ENVELOPE_KEY in body


def unwrap_envelope(body: dict) -> Tuple[str, Dict[str, List[str]]]:
    """
    Extract MMIF and normalized parameters from an envelope.

    :param body: parsed JSON dict with ``"parameters"`` and ``"mmif"``
    :returns: tuple of (mmif_json_string, normalized_params)
    :rtype: Tuple[str, Dict[str, List[str]]]
    :raises EnvelopeError: if ``"mmif"`` key is missing or
        ``"parameters"`` is not a dict
    """
    params = body.get(ENVELOPE_KEY)
    if not isinstance(params, dict):
        raise EnvelopeError(
            f'"{ENVELOPE_KEY}" must be a JSON object, '
            f'got {type(params).__name__}'
        )
    if MMIF_KEY not in body:
        raise EnvelopeError(
            f'Envelope is missing required "{MMIF_KEY}" key'
        )
    mmif_str = json.dumps(body[MMIF_KEY])
    return mmif_str, normalize_params(params)


def unwrap_if_envelope(data, runtime_params):
    """
    If ``data`` is (or decodes to) an envelope, return the inner MMIF
    together with envelope parameters merged under the explicitly-passed
    ``runtime_params`` (so query-string / CLI flags take priority). If
    ``data`` is not an envelope, return it unchanged.

    This is the single entry point used by every execution path
    (HTTP, CLI, direct Python API) so envelope handling is uniform
    regardless of how the app is invoked.

    :param data: raw input -- ``bytes``, ``str``, or ``dict``
    :param runtime_params: explicitly-passed parameters that override
        envelope parameters on key collision
    :returns: tuple of (mmif_or_original_data, effective_params)
    :raises EnvelopeError: if ``data`` is a malformed envelope
    """
    raw = data.decode('utf-8') if isinstance(data, bytes) else data
    body = raw
    if isinstance(raw, str):
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return data, runtime_params
    if is_envelope(body):
        inner_mmif, envelope_params = unwrap_envelope(body)
        return inner_mmif, {**envelope_params, **runtime_params}
    return data, runtime_params


def create_envelope(
    mmif: Union[str, dict, Mmif],
    parameters: Optional[dict] = None,
) -> str:
    """
    Create a JSON envelope string wrapping MMIF and parameters.

    :param mmif: MMIF as a string, dict, or
        :class:`~mmif.serialize.mmif.Mmif` object
    :param parameters: parameter dict with JSON-native values
    :returns: JSON string of the envelope
    :rtype: str
    """
    if isinstance(mmif, Mmif):
        mmif_obj = json.loads(mmif.serialize())
    elif isinstance(mmif, str):
        mmif_obj = json.loads(mmif)
    else:
        mmif_obj = mmif
    envelope = {
        ENVELOPE_KEY: parameters if parameters is not None else {},
        MMIF_KEY: mmif_obj,
    }
    return json.dumps(envelope)


# -- CLI interface ---------------------------------------------------

def describe_argparser():
    """
    :returns: tuple of (one-line help, detailed description)
    """
    oneliner = (
        'create a JSON envelope wrapping MMIF and runtime parameters'
    )
    detailed = (
        'Reads a JSON parameter file and an MMIF file (or stdin), '
        'combines them into a JSON envelope, and writes the result '
        'to stdout. The envelope can be POSTed directly to a CLAMS '
        'app HTTP endpoint.'
    )
    return oneliner, detailed


def prep_argparser(**kwargs):
    """
    :returns: argparse.ArgumentParser for the envelop subcommand
    """
    parser = argparse.ArgumentParser(
        description=describe_argparser()[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        **kwargs,
    )
    parser.add_argument(
        'PARAMS_FILE',
        type=argparse.FileType('r'),
        help='Path to a JSON file containing runtime parameters.',
    )
    parser.add_argument(
        'MMIF_FILE',
        nargs='?',
        type=argparse.FileType('r'),
        default=None if sys.stdin.isatty() else sys.stdin,
        help=(
            'Path to the input MMIF file, or stdin if omitted. '
            'Use "-" to explicitly read from stdin.'
        ),
    )
    return parser


def main(args):
    """
    CLI entry point. Reads params JSON and MMIF, writes envelope
    JSON to stdout.
    """
    if args.MMIF_FILE is None:
        print(
            'Error: no MMIF input provided '
            '(pass a file path or pipe to stdin)',
            file=sys.stderr,
        )
        sys.exit(1)
    params = json.load(args.PARAMS_FILE)
    mmif_str = args.MMIF_FILE.read()
    print(create_envelope(mmif_str, parameters=params))
