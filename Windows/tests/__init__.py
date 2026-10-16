import os
import tempfile

# Tests schreiben nie in das echte Profil.
_home = tempfile.mkdtemp(prefix="bluey-test-")
os.environ["APPDATA"] = _home
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
