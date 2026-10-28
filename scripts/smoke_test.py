"""Smoke test: log in as admin and hit critical endpoints.

Usage:
    E2E_PORTAL_URL=http://127.0.0.1:8000 E2E_USERNAME=admin E2E_PASSWORD=... python scripts/smoke_test.py
"""
import os
import sys
import urllib.request
import urllib.error
import json
import http.cookiejar

BASE = os.getenv("E2E_PORTAL_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.getenv("E2E_USERNAME", "admin")
PASSWORD = os.getenv("E2E_PASSWORD", "")

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, json.loads(body) if body else None


def check(name, fn):
    try:
        ok = fn()
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        return ok
    except Exception as exc:
        print(f"FAIL: {name} -> {exc}")
        return False


def main():
    results = []
    results.append(check("login", lambda: request("POST", "/api/v1/auth/login", {"username": USERNAME, "password": PASSWORD})[0] == 200))
    results.append(check("auth/me", lambda: request("GET", "/api/v1/auth/me")[0] == 200))
    results.append(check("shifts list", lambda: request("GET", "/api/v1/shifts?limit=5")[0] == 200))
    results.append(check("users list (admin)", lambda: request("GET", "/api/v1/users?limit=5")[0] == 200))
    results.append(check("audit logs", lambda: request("GET", "/api/v1/audit-logs?limit=5")[0] == 200))
    results.append(check("uploads list", lambda: request("GET", "/api/v1/uploads")[0] == 200))
    results.append(check("healthz", lambda: request("GET", "/healthz")[0] == 200))
    if all(results):
        print("All smoke checks passed.")
        sys.exit(0)
    print("Some smoke checks failed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
