import json
import re
import time

import httpx


def execute_relay_request(method: str, url: str, headers: dict = None, body: str = None, timeout: int = 30):
    """
    Executes the outbound HTTP request on behalf of the client.
    """
    headers = headers or {}
    start_time = time.perf_counter()

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                content=body if body else None
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Determine status color category
        status_code = response.status_code
        status_category = (
            "success" if 200 <= status_code < 300 else
            "redirect" if 300 <= status_code < 400 else
            "client_error" if 400 <= status_code < 500 else "server_error"
        )

        return {
            "status_code": status_code,
            "status_text": response.reason_phrase,
            "status_category": status_category,  # Useful for UI badge styling
            "elapsed_ms": elapsed_ms,
            "response_size_bytes": len(response.content),
            "headers": dict(response.headers),
            "body": response.text,
            "error": None
        }

    except httpx.RequestError as exc:
        return {
            "status_code": 0,
            "status_text": "Connection Failure",
            "status_category": "server_error",
            "elapsed_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "response_size_bytes": 0,
            "headers": {},
            "body": "",
            "error": str(exc)
        }


def resolve_env_variables(text: str, environment_vars: dict) -> str:
    """
    Replaces mustache syntax {{var_name}} in strings with actual environment values.
    Example: {{baseUrl}}/users -> https://api.example.com/users
    """
    if not text or not environment_vars:
        return text

    def replace_match(match):
        var_name = match.group(1).strip()
        return str(environment_vars.get(var_name, match.group(0)))

    # Matches {{ variable_name }}
    pattern = r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}'
    return re.sub(pattern, replace_match, text)


import base64


def apply_auth_headers(headers: dict, auth_type: str, auth_data: dict) -> dict:
    """
    Appends auth headers based on selected auth type.
    """
    headers = headers.copy()

    if auth_type == "bearer":
        token = auth_data.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_type == "basic":
        username = auth_data.get("username", "")
        password = auth_data.get("password", "")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    elif auth_type == "api_key":
        key = auth_data.get("key", "")
        value = auth_data.get("value", "")
        add_to = auth_data.get("add_to", "header")  # 'header' or 'query'
        if key and value and add_to == "header":
            headers[key] = value

    return headers


def generate_code_snippet(method: str, url: str, headers: dict = None, body: str = None, language: str = "curl") -> str:
    """
    Generates cURL, Python, or JavaScript fetch snippets.
    """
    headers = headers or {}

    if language == "curl":
        cmd = [f"curl --request {method.upper()} '{url}'"]
        for k, v in headers.items():
            cmd.append(f"  --header '{k}: {v}'")
        if body:
            cmd.append(f"  --data '{body}'")
        return " \\\n".join(cmd)

    elif language == "python":
        headers_str = json.dumps(headers, indent=4) if headers else "{}"
        body_str = f"data = {json.dumps(body)}" if body else "data = None"
        return f"""import requests

url = "{url}"
headers = {headers_str}
{body_str}

response = requests.request("{method.upper()}", url, headers=headers, data=data)
print(response.status_code)
print(response.text)
"""

    elif language == "javascript":
        opts = {"method": method.upper(), "headers": headers}
        if body:
            opts["body"] = body
        return f"""fetch("{url}", {json.dumps(opts, indent=2)})
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));"""

    return ""

import shlex

def parse_curl_command(curl_string: str) -> dict:
    """
    Parses a basic cURL string into a structured Relay request dictionary.
    """
    try:
        tokens = shlex.split(curl_string)
    except Exception:
        return {"error": "Invalid cURL format"}

    method = "GET"
    url = ""
    headers = {}
    body = ""

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("curl", "\\"):
            i += 1
            continue
        elif token in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            i += 2
        elif token in ("-H", "--header") and i + 1 < len(tokens):
            header_line = tokens[i + 1]
            if ":" in header_line:
                k, v = header_line.split(":", 1)
                headers[k.strip()] = v.strip()
            i += 2
        elif token in ("-d", "--data", "--data-raw") and i + 1 < len(tokens):
            body = tokens[i + 1]
            if method == "GET":
                method = "POST"
            i += 2
        elif token.startswith("http://") or token.startswith("https://"):
            url = token
            i += 1
        else:
            i += 1

    return {"method": method, "url": url, "headers": headers, "body": body}
def extract_json_path(response_json: dict, path_key: str):
    """
    Simple dot-notation extraction (e.g., "data.token" or "access_token").
    """
    try:
        keys = path_key.split(".")
        value = response_json
        for k in keys:
            value = value[k]
        return str(value)
    except (KeyError, TypeError):
        return None
from bs4 import BeautifulSoup


def is_html_response(headers: dict, body: str) -> bool:
    """
    Decides whether a response should get the HTML preview/table/extract
    treatment, based on the Content-Type header first, falling back to
    sniffing the body for a doctype/html tag.
    """
    content_type = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            content_type = v.lower()
            break
    if "html" in content_type:
        return True
    stripped = body.strip().lower()
    return stripped.startswith("<!doctype html") or stripped.startswith("<html")


def extract_html_tables(html_text: str, max_tables: int = 10, max_rows: int = 200):
    """
    Parses every <table> in the document into plain row/column text data
    the client can render as a real table (and copy out as CSV).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    tables = []
    for table in soup.find_all("table")[:max_tables]:
        rows = []
        for tr in table.find_all("tr")[:max_rows]:
            cells = tr.find_all(["td", "th"])
            rows.append([c.get_text(strip=True) for c in cells])
        rows = [r for r in rows if r]
        if rows:
            tables.append({"rows": rows})
    return tables


def extract_html_path(html_text: str, selector: str):
    """
    Pulls a value out of an HTML document via CSS selector, Scrapy-style:
      "h1.title"               -> text content of the first match
      "h1.title::text"         -> same, explicit
      "a.profile::attr(href)"  -> the href attribute of the first match
      "input[name=csrfmiddlewaretoken]::attr(value)" -> its value attribute
    """
    if not selector:
        return None

    attr_name = None
    clean_selector = selector.strip()
    if clean_selector.endswith("::text"):
        clean_selector = clean_selector[: -len("::text")]
    elif "::attr(" in clean_selector:
        clean_selector, attr_part = clean_selector.split("::attr(", 1)
        attr_name = attr_part.rstrip(")")

    try:
        soup = BeautifulSoup(html_text, "html.parser")
        el = soup.select_one(clean_selector.strip())
    except Exception:
        return None

    if el is None:
        return None

    if attr_name:
        return el.get(attr_name)
    return el.get_text(strip=True)