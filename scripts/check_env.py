#!/usr/bin/env python3
"""
Check prerequisites for the Shopify -> QBO sync pipeline.

Outputs a JSON report and human-readable summary of:
  - Node.js version (requires 18+)
  - Python version (requires 3.10+)
  - npm/npx availability
  - git availability
  - Claude CLI availability
  - Existing MCP server configurations

Exit code 0 if all required checks pass, 1 otherwise.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    """Run a command and return (exit_code, stdout)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        return result.returncode, result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1, ""


def parse_version(version_str: str) -> tuple[int, ...] | None:
    """Extract version numbers from a version string like 'v20.11.0' or 'Python 3.12.1'."""
    match = re.search(r"(\d+)\.(\d+)\.?(\d*)", version_str)
    if match:
        parts = [int(x) for x in match.groups() if x]
        return tuple(parts)
    return None


def check_node() -> dict:
    """Check Node.js installation and version."""
    code, output = run_cmd(["node", "--version"])
    if code != 0:
        return {"name": "Node.js", "required": "18+", "found": None, "passed": False,
                "fix": "brew install node (macOS) or visit https://nodejs.org"}
    version = parse_version(output)
    passed = version is not None and version[0] >= 18
    return {"name": "Node.js", "required": "18+", "found": output, "passed": passed,
            "fix": "Update Node.js to 18+ via your package manager" if not passed else None}


def check_python() -> dict:
    """Check Python installation and version."""
    version = sys.version_info
    found = f"{version.major}.{version.minor}.{version.micro}"
    passed = (version.major, version.minor) >= (3, 10)
    return {"name": "Python", "required": "3.10+", "found": found, "passed": passed,
            "fix": "brew install python@3.12 (macOS)" if not passed else None}


def check_npx() -> dict:
    """Check npx availability."""
    code, output = run_cmd(["npx", "--version"])
    passed = code == 0
    return {"name": "npx", "required": "any", "found": output if passed else None, "passed": passed,
            "fix": "npm install -g npx (comes with Node.js)" if not passed else None}


def check_git() -> dict:
    """Check git availability."""
    code, output = run_cmd(["git", "--version"])
    passed = code == 0
    version = output.replace("git version ", "") if passed else None
    return {"name": "git", "required": "any", "found": version, "passed": passed,
            "fix": "xcode-select --install (macOS) or visit https://git-scm.com" if not passed else None}


def check_claude_cli() -> dict:
    """Check Claude CLI availability."""
    code, output = run_cmd(["claude", "--version"])
    passed = code == 0
    return {"name": "Claude CLI", "required": "any", "found": output if passed else None, "passed": passed,
            "fix": "Visit https://docs.anthropic.com/en/docs/claude-code" if not passed else None}


def check_mcp_servers() -> dict:
    """Check for existing MCP server configurations."""
    code, output = run_cmd(["claude", "mcp", "list"])
    servers = {}
    if code == 0 and output:
        for line in output.splitlines():
            line = line.strip()
            if line and not line.startswith("Name") and not line.startswith("-"):
                parts = line.split()
                if parts:
                    name = parts[0].lower()
                    if "shopify" in name:
                        servers["shopify"] = True
                    if "quickbooks" in name or "qbo" in name:
                        servers["quickbooks"] = True
    return {
        "shopify_configured": servers.get("shopify", False),
        "quickbooks_configured": servers.get("quickbooks", False),
    }


def check_qbo_credentials() -> dict:
    """Check if QBO credentials file exists."""
    cred_path = Path.home() / ".quickbooks-mcp" / "credentials.json"
    exists = cred_path.exists()
    has_tokens = False
    if exists:
        try:
            with open(cred_path) as f:
                creds = json.load(f)
            has_tokens = bool(creds.get("access_token"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "credentials_file": exists,
        "has_tokens": has_tokens,
        "path": str(cred_path),
    }


def main():
    checks = [check_node(), check_python(), check_npx(), check_git(), check_claude_cli()]
    mcp_status = check_mcp_servers()
    qbo_creds = check_qbo_credentials()

    all_passed = all(c["passed"] for c in checks)

    report = {
        "prerequisites": checks,
        "all_passed": all_passed,
        "existing_setup": {
            "mcp_servers": mcp_status,
            "qbo_credentials": qbo_creds,
        },
    }

    # Human-readable output
    print("=" * 50)
    print("  Shopify -> QBO Sync: Prerequisite Check")
    print("=" * 50)

    for check in checks:
        icon = "+" if check["passed"] else "x"
        version = check["found"] or "not found"
        print(f"  [{icon}] {check['name']:<12} {version:<20} (requires {check['required']})")
        if check.get("fix"):
            print(f"      Fix: {check['fix']}")

    print()
    print("  Existing Setup:")
    print(f"    Shopify MCP:  {'configured' if mcp_status['shopify_configured'] else 'not configured'}")
    print(f"    QBO MCP:      {'configured' if mcp_status['quickbooks_configured'] else 'not configured'}")
    print(f"    QBO creds:    {'found' if qbo_creds['credentials_file'] else 'not found'}"
          + (f" (tokens: {'yes' if qbo_creds['has_tokens'] else 'no'})" if qbo_creds['credentials_file'] else ""))

    print()
    if all_passed:
        print("  All prerequisites met. Ready to proceed.")
    else:
        failed = [c["name"] for c in checks if not c["passed"]]
        print(f"  Missing: {', '.join(failed)}")
        print("  Install the missing prerequisites before continuing.")

    print("=" * 50)

    # JSON output to stdout (after the human-readable part)
    print("\n__JSON_REPORT__")
    print(json.dumps(report, indent=2))

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
