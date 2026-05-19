import json
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")

if not file_path or not file_path.endswith(".py") or not Path(file_path).is_file():
    sys.exit(0)

subprocess.run(
    [sys.executable, "-m", "black", "--quiet", file_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    check=False,
)
sys.exit(0)
