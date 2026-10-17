"""Write the API's OpenAPI schema to a file. Used by `python dev.py types` and CI.

Always writes LF line endings so the file is identical on Windows and macOS.
"""

import json
import os
import sys
from pathlib import Path

os.environ["PLANIT_MOCK"] = "1"

from planit.api.main import app  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1])
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(app.openapi(), indent=2) + "\n")


if __name__ == "__main__":
    main()
