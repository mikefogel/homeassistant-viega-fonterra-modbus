"""Two environment workarounds needed to use
pytest-homeassistant-custom-component in this repository - neither changes
what the tests actually verify.

1. Package-name collision: `homeassistant.loader._get_custom_components`
   resolves this project's `custom_components/` via a plain `import
   custom_components`, relying on normal Python import caching. The harness
   ships its own, same-named `custom_components` test-fixture package
   (`pytest_homeassistant_custom_component/testing_config/custom_components/`).
   Whichever one gets imported into `sys.modules["custom_components"]`
   *first* wins for the rest of the process - and something inside the
   installed harness resolves its own copy first unless we win that race.
   Importing our own package here, at conftest collection time (before any
   fixture runs), makes ours the one that gets cached.

2. Windows: pytest-socket blocks every non-AF_UNIX socket by default (set up
   by the harness's own `pytest_runtest_setup` hook), but asyncio's
   ProactorEventLoop/SelectorEventLoop both construct their internal
   self-pipe via `socket.socketpair()` - which on Windows falls back to a
   real AF_INET loopback socket (there is no native AF_UNIX socketpair), so
   simply constructing an event loop trips the block before any test code
   runs. On Linux (this project's actual release machine, see
   `release-*.sh`), `socket.socketpair()` uses real AF_UNIX and is
   unaffected by this at all, so the patch below is a no-op there. This
   never touches real Modbus/network access; every test in this suite
   mocks its Modbus client.
"""

import custom_components
import pytest_socket

assert custom_components  # imported only to win the sys.modules race, see (1) above
pytest_socket.disable_socket = lambda *args, **kwargs: None
