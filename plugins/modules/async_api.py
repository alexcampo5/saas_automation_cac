#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2024, Your Name
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: async_api_calls
short_description: Perform concurrent async HTTP API calls to a list of URLs
version_added: "1.0.0"
description:
  - Takes a list of URLs and a concurrency limit, fires async HTTP requests
    up to C(concurrency) at a time, and returns all responses.
  - Supports GET, POST, PUT, PATCH, DELETE methods.
  - Per-request headers, body, and timeout are configurable.
  - Failed requests are captured in the results rather than failing the task
    by default (controlled by C(fail_on_error)).

options:
  urls:
    description:
      - List of URL strings, or list of request objects.
      - A request object may contain C(url), C(method), C(headers), C(body),
        and C(timeout) keys to override the module-level defaults.
    type: list
    elements: raw
    required: true

  concurrency:
    description:
      - Maximum number of simultaneous in-flight requests.
      - Defaults to 10.
    type: int
    default: 10

  method:
    description:
      - Default HTTP method for all requests.
      - Can be overridden per-request via the request object.
    type: str
    default: GET
    choices: [GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS]

  headers:
    description:
      - Default HTTP headers sent with every request.
      - Merged with (and overridden by) per-request headers.
    type: dict
    default: {}

  body:
    description:
      - Default request body (string or dict).
      - Dicts are JSON-serialised automatically.
    type: raw
    default: null

  timeout:
    description:
      - Default per-request timeout in seconds.
    type: float
    default: 30.0

  validate_certs:
    description:
      - Whether to verify TLS certificates.
    type: bool
    default: true

  fail_on_error:
    description:
      - When true, the task fails if ANY request returns a non-2xx status
        or raises an exception.
      - When false (default), errors are captured in the result's C(error)
        field and the task succeeds.
    type: bool
    default: false

  follow_redirects:
    description:
      - Whether to follow HTTP redirects.
    type: bool
    default: true

author:
  - Your Name (@yourhandle)

requirements:
  - python >= 3.7
  - aiohttp >= 3.8
'''

EXAMPLES = r'''
# Simple GET requests with default concurrency
- name: Fetch multiple endpoints
  async_api_calls:
    urls:
      - https://api.example.com/users/1
      - https://api.example.com/users/2
      - https://api.example.com/users/3
  register: result

# Mixed methods and per-request overrides
- name: Mixed HTTP methods
  async_api_calls:
    concurrency: 5
    headers:
      Authorization: "Bearer {{ vault_token }}"
      Content-Type: application/json
    urls:
      - url: https://api.example.com/items
        method: GET
      - url: https://api.example.com/items
        method: POST
        body:
          name: widget
          price: 9.99
      - url: https://api.example.com/items/42
        method: DELETE
        timeout: 10
  register: api_results

# Use the results
- name: Show all responses
  debug:
    msg: "{{ item.url }} → {{ item.status }}"
  loop: "{{ api_results.responses }}"

# Filter successful responses
- name: Process successful responses only
  debug:
    msg: "{{ item.json }}"
  loop: "{{ api_results.responses | selectattr('ok', 'equalto', true) | list }}"
'''

RETURN = r'''
responses:
  description: List of response objects, one per input URL, in input order.
  returned: always
  type: list
  elements: dict
  contains:
    url:
      description: The URL that was requested.
      type: str
    method:
      description: HTTP method used.
      type: str
    status:
      description: HTTP status code, or -1 on connection error.
      type: int
    ok:
      description: True when status is in the 2xx range.
      type: bool
    headers:
      description: Response headers as a dict.
      type: dict
    body:
      description: Raw response body as a string.
      type: str
    json:
      description: Parsed JSON body, or null if not valid JSON.
      type: raw
    elapsed:
      description: Wall-clock seconds for this request.
      type: float
    error:
      description: Error message string, or null on success.
      type: str

summary:
  description: Aggregate statistics for all requests.
  returned: always
  type: dict
  contains:
    total:
      description: Total number of requests.
      type: int
    succeeded:
      description: Number of 2xx responses.
      type: int
    failed:
      description: Number of non-2xx or errored responses.
      type: int
    elapsed_total:
      description: Total wall-clock time in seconds (not sum of individual).
      type: float
'''

# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

import asyncio
import json
import ssl
import time
import traceback

from ansible.module_utils.basic import AnsibleModule

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


def _normalise_request(item, defaults):
    """
    Accept either a plain URL string or a dict with request fields.
    Returns a normalised dict merged with module-level defaults.
    """
    if isinstance(item, str):
        item = {"url": item}

    req = {
        "url":     item.get("url"),
        "method":  (item.get("method") or defaults["method"]).upper(),
        "headers": {**defaults["headers"], **(item.get("headers") or {})},
        "body":    item.get("body", defaults["body"]),
        "timeout": float(item.get("timeout") or defaults["timeout"]),
    }

    if req["url"] is None:
        raise ValueError("Each request entry must contain a 'url' key.")

    return req


async def _do_request(session, req, semaphore):
    """Execute a single HTTP request inside the semaphore guard."""
    result = {
        "url":     req["url"],
        "method":  req["method"],
        "status":  -1,
        "ok":      False,
        "headers": {},
        "body":    "",
        "json":    None,
        "elapsed": 0.0,
        "error":   None,
    }

    body_arg = {}
    if req["body"] is not None:
        if isinstance(req["body"], dict):
            body_arg["json"] = req["body"]
        else:
            body_arg["data"] = str(req["body"])

    t0 = time.monotonic()
    try:
        async with semaphore:
            timeout = aiohttp.ClientTimeout(total=req["timeout"])
            async with session.request(
                method=req["method"],
                url=req["url"],
                headers=req["headers"],
                timeout=timeout,
                **body_arg,
            ) as resp:
                body_text = await resp.text(errors="replace")
                result["status"]  = resp.status
                result["ok"]      = 200 <= resp.status < 300
                result["headers"] = dict(resp.headers)
                result["body"]    = body_text
                try:
                    result["json"] = json.loads(body_text)
                except (json.JSONDecodeError, ValueError):
                    result["json"] = None
    except asyncio.TimeoutError:
        result["error"] = f"Request timed out after {req['timeout']}s"
    except aiohttp.ClientSSLError as exc:
        result["error"] = f"SSL error: {exc}"
    except aiohttp.ClientConnectionError as exc:
        result["error"] = f"Connection error: {exc}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Unexpected error: {traceback.format_exc(limit=3)}"
    finally:
        result["elapsed"] = round(time.monotonic() - t0, 4)

    return result


async def _run_all(requests, concurrency, validate_certs, follow_redirects):
    semaphore = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(ssl=None if validate_certs else False)

    async with aiohttp.ClientSession(
        connector=connector,
        allow_redirects=follow_redirects,
    ) as session:
        tasks = [
            _do_request(session, req, semaphore)
            for req in requests
        ]
        results = await asyncio.gather(*tasks)

    return list(results)


def main():
    module_args = dict(
        urls=dict(type="list", elements="raw", required=True),
        concurrency=dict(type="int", default=10),
        method=dict(
            type="str", default="GET",
            choices=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        ),
        headers=dict(type="dict", default={}),
        body=dict(type="raw", default=None),
        timeout=dict(type="float", default=30.0),
        validate_certs=dict(type="bool", default=True),
        fail_on_error=dict(type="bool", default=False),
        follow_redirects=dict(type="bool", default=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    if not HAS_AIOHTTP:
        module.fail_json(
            msg="The 'aiohttp' Python library is required for this module. "
                "Install it with: pip install aiohttp"
        )

    concurrency = module.params["concurrency"]
    if concurrency < 1:
        module.fail_json(msg="'concurrency' must be at least 1.")

    defaults = {
        "method":  module.params["method"],
        "headers": module.params["headers"],
        "body":    module.params["body"],
        "timeout": module.params["timeout"],
    }

    try:
        requests = [
            _normalise_request(item, defaults)
            for item in module.params["urls"]
        ]
    except (ValueError, TypeError) as exc:
        module.fail_json(msg=f"Invalid URL entry: {exc}")

    wall_start = time.monotonic()
    responses = asyncio.run(
        _run_all(
            requests=requests,
            concurrency=concurrency,
            validate_certs=module.params["validate_certs"],
            follow_redirects=module.params["follow_redirects"],
        )
    )
    wall_elapsed = round(time.monotonic() - wall_start, 4)

    succeeded = sum(1 for r in responses if r["ok"])
    failed    = len(responses) - succeeded

    summary = {
        "total":         len(responses),
        "succeeded":     succeeded,
        "failed":        failed,
        "elapsed_total": wall_elapsed,
    }

    if module.params["fail_on_error"] and failed:
        errors = [
            f"{r['url']}: status={r['status']} error={r['error']}"
            for r in responses
            if not r["ok"]
        ]
        module.fail_json(
            msg=f"{failed} request(s) failed.",
            failed_requests=errors,
            responses=responses,
            summary=summary,
        )

    module.exit_json(
        changed=False,
        responses=responses,
        summary=summary,
    )


if __name__ == "__main__":
    main()