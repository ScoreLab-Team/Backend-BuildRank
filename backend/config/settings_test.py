from .settings import *  # noqa: F401, F403

# Disable real GetStream calls during tests.
# Signals that check _stream_is_configured() will short-circuit, preventing
# real HTTP calls to GetStream and avoiding "user was deleted" noise.
STREAM_API_KEY = ""
STREAM_API_SECRET = ""
