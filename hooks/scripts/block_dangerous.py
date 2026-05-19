import json
import sys

# Read the tool call info from harness
data = json.load(sys.stdin)

command = data.get("tool_input", {}).get("command", "")

# Files to protect
protected_files = [
    "spendly.db",
    "expense_tracker.db",
    ".env",
    "migrations"
]

# Dangerous commands
dangerous_commands = ["rm ", "del ", "rmdir", "rd "]

for dangerous in dangerous_commands:
    if dangerous in command:
        for protected in protected_files:
            if protected in command:
                print(f"BLOCKED: Cannot delete protected file: {protected}")
                sys.exit(2)

sys.exit(0)