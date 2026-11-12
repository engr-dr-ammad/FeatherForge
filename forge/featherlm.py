"""Experimental evaluation-only adapter for FeatherLM's completion API."""

import json
import os
import urllib.request

CASES = [
    (
        "planning",
        "Return only JSON for a plan with dependencies: implement, test depends on implement, review depends on test.",
        lambda x: isinstance(x, dict)
        and x.get("dependencies")
        == {"implement": [], "test": ["implement"], "review": ["test"]},
    ),
    (
        "tool_selection",
        'Allowed tools are read_file and run_tests. Return only JSON selecting read_file with path index.html. Shape: {"tool":"read_file","arguments":{"path":"index.html"}}',
        lambda x: x == {"tool": "read_file", "arguments": {"path": "index.html"}},
    ),
    (
        "coding",
        'Return only JSON containing a Python function source in code that returns a + b. Shape: {"code":"def add(a, b):\\n    return a + b"}',
        lambda x: isinstance(x, dict)
        and x.get("code", "").strip() == "def add(a, b):\n    return a + b",
    ),
]


def probe():
    base = os.getenv("FORGE_FEATHERLM_URL", "http://127.0.0.1:8003/v1").rstrip("/")
    model = os.getenv("FORGE_FEATHERLM_MODEL", "runs/featherlm-nano/best")
    results = []
    for name, prompt, judge in CASES:
        request = urllib.request.Request(
            base + "/completions",
            data=json.dumps(
                {
                    "model": model,
                    "prompt": prompt,
                    "max_tokens": 160,
                    "temperature": 0,
                    "stream": False,
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + os.getenv("FORGE_FEATHERLM_KEY", "local"),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                sample = json.load(response)["choices"][0]["text"]
            try:
                passed = judge(json.loads(sample))
            except (ValueError, TypeError):
                passed = False
            results.append({"case": name, "passed": passed, "sample": sample[:4000]})
        except Exception as exc:
            results.append({"case": name, "passed": False, "error": type(exc).__name__})
    return {
        "experimental": True,
        "model": model,
        "cases": results,
        "implementation_eligible": False,
        "limitations": "Three smoke probes are not a coding benchmark or a promotion gate. No generated code is executed and no tools are granted. Maintainer-reviewed held-out evaluation is required.",
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
