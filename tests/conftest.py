"""
Compatibility shim: httpcore 1.0.x changed request.method from str to bytes,
but respx 0.21.1 was written for the older str API. Patching Method.parse to
decode bytes makes respx work correctly with the installed httpcore version.
"""
from respx.patterns import Method

_orig_method_parse = Method.parse


def _method_parse_compat(self, request):  # type: ignore[override]
    method = _orig_method_parse(self, request)
    if isinstance(method, bytes):
        return method.decode("ascii").upper()
    return method


Method.parse = _method_parse_compat  # type: ignore[method-assign]
