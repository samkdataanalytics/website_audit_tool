import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from website_audit_tool.web.app import app  # noqa: F401  (Vercel picks up `app`)
