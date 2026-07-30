import json
import re

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from engine import (
    resolve_env_variables,
    apply_auth_headers,
    execute_relay_request,
    generate_code_snippet,
    parse_curl_command,
    extract_json_path,
    is_html_response,
    extract_html_tables,
    extract_html_path,
)
from .models import Collection, Environment, SavedRequest, RequestHistory, Flow, FlowStep


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email_or_username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=email_or_username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials. Please try again.')

    return render(request, 'login.html')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if not username:
            messages.error(request, 'Username is required.')
            return render(request, 'signup.html')

        if password != confirm_password:
            messages.error(request, "Passwords don't match.")
            return render(request, 'signup.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username is already taken.')
            return render(request, 'signup.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email is already registered.')
            return render(request, 'signup.html')

        user = User.objects.create_user(username=username, email=email, password=password)
        login(request, user)
        return redirect('dashboard')

    return render(request, 'signup.html')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_env_vars(request, env_id=None):
    base_env_vars = {}
    if env_id and request.user.is_authenticated:
        env = Environment.objects.filter(owner=request.user, id=env_id).first()
        if env:
            base_env_vars = env.get_vars()
    extracted = request.session.get('relay_extracted_vars', {})
    return {**base_env_vars, **extracted}


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

@login_required
def workspace(request):
    collections = Collection.objects.filter(owner=request.user).prefetch_related('requests', 'environments')
    environments = Environment.objects.filter(owner=request.user)
    flows = Flow.objects.filter(owner=request.user).prefetch_related('steps__saved_request')
    history = RequestHistory.objects.filter(owner=request.user)[:30]

    # Get saved assertions from session or use defaults
    assertions = request.session.get('relay_assertions', [
        {'type': 'status', 'operator': 'equals', 'expected': '200', 'path': '', 'message': 'Status should be 200'},
        {'type': 'response_time', 'operator': 'less_than', 'expected': '500', 'path': '',
         'message': 'Response time < 500ms'},
    ])

    context = {
        "collections": collections,
        "environments": environments,
        "environments_json": [
            {"id": e.id, "name": e.name, "collection_id": e.collection_id} for e in environments
        ],
        "flows": flows,
        "history": history,
        "extracted_vars": request.session.get('relay_extracted_vars', {}),
        "assertions": assertions,  # Add this
    }
    return render(request, "workspace.html", context)


@login_required
def send_request_api(request):
    if request.method != "POST":
        return HttpResponse(status=400)

    method = request.POST.get("method", "GET")
    raw_url = request.POST.get("url", "")
    auth_type = request.POST.get("auth_type", "none")
    bearer_token = request.POST.get("bearer_token", "")
    basic_username = request.POST.get("basic_username", "")
    basic_password = request.POST.get("basic_password", "")
    api_key_name = request.POST.get("api_key_name", "")
    api_key_value = request.POST.get("api_key_value", "")
    req_body = request.POST.get("body", "")
    saved_request_id = request.POST.get("saved_request_id", "").strip()  # NEW

    header_keys = request.POST.getlist("header_keys[]")
    header_vals = request.POST.getlist("header_vals[]")
    headers = {k: v for k, v in zip(header_keys, header_vals) if k.strip()}

    env_vars = _session_env_vars(request, request.POST.get("active_env_id"))

    url = resolve_env_variables(raw_url, env_vars)
    headers = {resolve_env_variables(k, env_vars): resolve_env_variables(v, env_vars) for k, v in headers.items()}
    req_body = resolve_env_variables(req_body, env_vars) if req_body else req_body

    if req_body and not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/json"

    auth_data = {}
    if auth_type == "bearer":
        auth_data = {"token": bearer_token}
    elif auth_type == "basic":
        auth_data = {"username": basic_username, "password": basic_password}
    elif auth_type == "api_key":
        auth_data = {"key": api_key_name, "value": api_key_value, "add_to": "header"}

    headers = apply_auth_headers(headers, auth_type, auth_data)

    response_data = execute_relay_request(method=method, url=url, headers=headers, body=req_body)

    raw_body = response_data.get("body", "")
    formatted_body = raw_body
    is_json = False
    try:
        parsed = json.loads(raw_body)
        formatted_body = json.dumps(parsed, indent=2)
        is_json = True
    except (ValueError, TypeError):
        pass

    response_data["formatted_body"] = formatted_body
    response_data["is_json"] = is_json

    is_html = False
    html_tables = []
    if not is_json:
        is_html = is_html_response(response_data.get("headers", {}), raw_body)
        if is_html:
            html_tables = extract_html_tables(raw_body)
            request.session['relay_last_response_html'] = raw_body
            request.session.modified = True

    snippets = {
        "curl": generate_code_snippet(method, url, headers, req_body, "curl"),
        "python": generate_code_snippet(method, url, headers, req_body, "python"),
        "javascript": generate_code_snippet(method, url, headers, req_body, "javascript"),
    }

    if is_json:
        request.session['relay_last_response_json'] = parsed
        request.session.modified = True

    if request.user.is_authenticated:
        saved_request_obj = None
        if saved_request_id:
            saved_request_obj = SavedRequest.objects.filter(
                collection__owner=request.user, id=saved_request_id
            ).first()
        RequestHistory.objects.create(
            owner=request.user,
            saved_request=saved_request_obj,
            method=method,
            url=url,
            headers_json=json.dumps([{"key": k, "val": v} for k, v in headers.items()]),
            body=req_body,
            auth_type=auth_type,
            auth_data_json=json.dumps(auth_data),
            status_code=response_data.get("status_code", 0),
            status_category=response_data.get("status_category", "server_error"),
            elapsed_ms=response_data.get("elapsed_ms", 0),
        )

    environments = Environment.objects.filter(owner=request.user) if request.user.is_authenticated else []

    return render(request, "partials/response_panel.html", {
        "res": response_data,
        "snippets": snippets,
        "is_json": is_json,
        "is_html": is_html,
        "html_tables": html_tables,
        "environments": environments,
    })


def import_curl_api(request):
    """
    Parses a pasted cURL command and returns the populated request-form
    fields as JSON so the client can fill the method/url/headers/body inputs.
    """
    if request.method != "POST":
        return HttpResponse(status=400)

    raw_curl = request.POST.get("curl_text", "")
    parsed = parse_curl_command(raw_curl)

    if "error" in parsed:
        return JsonResponse(parsed, status=400)

    return JsonResponse(parsed)


def extract_variable_api(request):
    if request.method != "POST":
        return HttpResponse(status=400)

    var_name = request.POST.get("var_name", "").strip()
    path_key = request.POST.get("path_key", "").strip()
    env_id = request.POST.get("env_id", "").strip()
    last_response = request.session.get('relay_last_response_json')

    if not var_name or not path_key:
        return JsonResponse({"error": "Both a variable name and a path are required."}, status=400)

    if last_response is None:
        return JsonResponse({"error": "No JSON response available yet — send a request first."}, status=400)

    value = extract_json_path(last_response, path_key)
    if value is None:
        return JsonResponse({"error": f"Could not find '{path_key}' in the last response."}, status=400)

    extracted = request.session.get('relay_extracted_vars', {})
    extracted[var_name] = value
    request.session['relay_extracted_vars'] = extracted
    request.session.modified = True

    if env_id and request.user.is_authenticated:
        env = Environment.objects.filter(owner=request.user, id=env_id).first()
        if env:
            env_vars = env.get_vars()
            env_vars[var_name] = value
            env.set_vars(env_vars)
            env.save()

    return JsonResponse({"var_name": var_name, "value": value, "extracted_vars": extracted})


@login_required
@require_POST
def create_collection_api(request):
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    if not name:
        return JsonResponse({"error": "Collection name is required."}, status=400)
    collection, created = Collection.objects.get_or_create(
        owner=request.user, name=name, defaults={"description": description}
    )
    if not created:
        return JsonResponse({"error": "A collection with that name already exists."}, status=400)
    return render(request, "partials/collections_list.html", {
        "collections": Collection.objects.filter(owner=request.user).prefetch_related('requests')
    })


@login_required
@require_POST
@csrf_exempt
def delete_collection_api(request, collection_id):
    Collection.objects.filter(owner=request.user, id=collection_id).delete()
    return render(request, "partials/collections_list.html", {
        "collections": Collection.objects.filter(owner=request.user).prefetch_related('requests')
    })


@login_required
@require_POST
def save_request_api(request):
    """
    Saves the CURRENT studio form state (method/url/headers/body/auth) into
    a collection. If collection_id is blank, uses/creates new_collection_name.
    """
    name = request.POST.get("name", "").strip()
    collection_id = request.POST.get("collection_id", "").strip()
    new_collection_name = request.POST.get("new_collection_name", "").strip()

    method = request.POST.get("method", "GET")
    url = request.POST.get("url", "")
    body = request.POST.get("body", "")
    auth_type = request.POST.get("auth_type", "none")

    header_keys = request.POST.getlist("header_keys[]")
    header_vals = request.POST.getlist("header_vals[]")
    headers = [{"key": k, "val": v} for k, v in zip(header_keys, header_vals) if k.strip()]

    auth_data = {
        "token": request.POST.get("bearer_token", ""),
        "username": request.POST.get("basic_username", ""),
        "password": request.POST.get("basic_password", ""),
        "key": request.POST.get("api_key_name", ""),
        "value": request.POST.get("api_key_value", ""),
    }

    if not name:
        return JsonResponse({"error": "Request name is required."}, status=400)

    if collection_id:
        collection = Collection.objects.filter(owner=request.user, id=collection_id).first()
        if not collection:
            return JsonResponse({"error": "Collection not found."}, status=404)
    elif new_collection_name:
        collection, _ = Collection.objects.get_or_create(owner=request.user, name=new_collection_name)
    else:
        return JsonResponse({"error": "Pick a collection or name a new one."}, status=400)

    SavedRequest.objects.create(
        collection=collection,
        name=name,
        method=method,
        url=url,
        headers_json=json.dumps(headers),
        body=body,
        auth_type=auth_type,
        auth_data_json=json.dumps(auth_data),
    )

    return render(request, "partials/collections_list.html", {
        "collections": Collection.objects.filter(owner=request.user).prefetch_related('requests')
    })


@login_required
def load_request_api(request, request_id):
    """Returns a saved request as JSON so Alpine can populate the studio form."""
    saved = SavedRequest.objects.filter(collection__owner=request.user, id=request_id).first()
    if not saved:
        return JsonResponse({"error": "Not found."}, status=404)
    auth = saved.get_auth_data()
    return JsonResponse({
        "method": saved.method,
        "url": saved.url,
        "headers": saved.get_headers(),
        "body": saved.body,
        "auth_type": saved.auth_type,
        "bearer_token": auth.get("token", ""),
        "basic_username": auth.get("username", ""),
        "basic_password": auth.get("password", ""),
        "api_key_name": auth.get("key", ""),
        "api_key_value": auth.get("value", ""),
    })


@login_required
@require_POST
def delete_request_api(request, request_id):
    SavedRequest.objects.filter(collection__owner=request.user, id=request_id).delete()
    return render(request, "partials/collections_list.html", {
        "collections": Collection.objects.filter(owner=request.user).prefetch_related('requests')
    })


@login_required
def history_list_api(request):
    history = RequestHistory.objects.filter(owner=request.user)[:50]
    return render(request, "partials/history_list.html", {"history": history})


@login_required
def load_history_api(request, history_id):
    entry = RequestHistory.objects.filter(owner=request.user, id=history_id).first()
    if not entry:
        return JsonResponse({"error": "Not found."}, status=404)
    auth = json.loads(entry.auth_data_json or "{}")
    return JsonResponse({
        "method": entry.method,
        "url": entry.url,
        "headers": entry.get_headers(),
        "body": entry.body,
        "auth_type": entry.auth_type,
        "bearer_token": auth.get("token", ""),
        "basic_username": auth.get("username", ""),
        "basic_password": auth.get("password", ""),
        "api_key_name": auth.get("key", ""),
        "api_key_value": auth.get("value", ""),
    })


@login_required
@require_POST
def save_history_to_collection_api(request, history_id):
    """Promote a one-off history entry into a saved request."""
    entry = RequestHistory.objects.filter(owner=request.user, id=history_id).first()
    if not entry:
        return JsonResponse({"error": "Not found."}, status=404)

    name = request.POST.get("name", "").strip() or f"{entry.method} {entry.url[:40]}"
    collection_id = request.POST.get("collection_id", "").strip()
    new_collection_name = request.POST.get("new_collection_name", "").strip()

    if collection_id:
        collection = Collection.objects.filter(owner=request.user, id=collection_id).first()
    elif new_collection_name:
        collection, _ = Collection.objects.get_or_create(owner=request.user, name=new_collection_name)
    else:
        return JsonResponse({"error": "Pick a collection or name a new one."}, status=400)

    SavedRequest.objects.create(
        collection=collection,
        name=name,
        method=entry.method,
        url=entry.url,
        headers_json=entry.headers_json,
        body=entry.body,
        auth_type=entry.auth_type,
        auth_data_json=entry.auth_data_json,
    )
    return render(request, "partials/collections_list.html", {
        "collections": Collection.objects.filter(owner=request.user).prefetch_related('requests')
    })


@login_required
@require_POST
def save_environment_api(request):
    name = request.POST.get("name", "").strip()
    collection_id = request.POST.get("collection_id", "").strip() or None
    vars_json = request.POST.get("vars_json", "{}")

    if not name:
        return JsonResponse({"error": "Environment name is required."}, status=400)

    env, _ = Environment.objects.update_or_create(
        owner=request.user, name=name, collection_id=collection_id,
        defaults={"variables_json": vars_json}
    )
    return JsonResponse({"ok": True, "id": env.id})


@login_required
def list_environments_api(request):
    envs = Environment.objects.filter(owner=request.user)
    return JsonResponse({
        "environments": [
            {"id": e.id, "name": e.name, "collection_id": e.collection_id, "vars": e.get_vars()}
            for e in envs
        ]
    })


@login_required
def saved_request_trend_api(request, request_id):
    saved = SavedRequest.objects.filter(collection__owner=request.user, id=request_id).first()
    if not saved:
        return JsonResponse({"error": "Not found."}, status=404)
    runs = RequestHistory.objects.filter(owner=request.user, saved_request=saved).order_by('created_at')[:30]
    return JsonResponse({
        "runs": [
            {
                "elapsed_ms": r.elapsed_ms,
                "status_code": r.status_code,
                "status_category": r.status_category,
                "created_at": r.created_at.strftime('%H:%M:%S'),
            }
            for r in runs
        ]
    })


@login_required
def export_collection_api(request, collection_id):
    collection = Collection.objects.filter(owner=request.user, id=collection_id).prefetch_related('requests').first()
    if not collection:
        return JsonResponse({"error": "Not found."}, status=404)

    data = {
        "name": collection.name,
        "description": collection.description,
        "requests": [
            {
                "name": r.name,
                "method": r.method,
                "url": r.url,
                "headers": r.get_headers(),
                "body": r.body,
                "auth_type": r.auth_type,
                "auth_data": r.get_auth_data(),
            }
            for r in collection.requests.all()
        ],
    }
    response = HttpResponse(json.dumps(data, indent=2), content_type="application/json")
    response['Content-Disposition'] = f'attachment; filename="{collection.name}.relay.json"'
    return response


@login_required
@require_POST
def import_collection_api(request):
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({"error": "No file uploaded."}, status=400)
    try:
        data = json.loads(file.read().decode('utf-8'))
    except Exception:
        return JsonResponse({"error": "Invalid JSON file."}, status=400)

    base_name = (data.get('name') or 'Imported Collection').strip() or 'Imported Collection'
    name = base_name
    n = 1
    while Collection.objects.filter(owner=request.user, name=name).exists():
        n += 1
        name = f"{base_name} ({n})"

    collection = Collection.objects.create(owner=request.user, name=name, description=data.get('description', ''))
    for r in data.get('requests', []):
        SavedRequest.objects.create(
            collection=collection,
            name=r.get('name', 'Untitled'),
            method=r.get('method', 'GET'),
            url=r.get('url', ''),
            headers_json=json.dumps(r.get('headers', [])),
            body=r.get('body', ''),
            auth_type=r.get('auth_type', 'none'),
            auth_data_json=json.dumps(r.get('auth_data', {})),
        )

    return render(request, "partials/collections_list.html", {
        "collections": Collection.objects.filter(owner=request.user).prefetch_related('requests', 'environments')
    })


def extract_html_variable_api(request):
    if request.method != "POST":
        return HttpResponse(status=400)

    var_name = request.POST.get("var_name", "").strip()
    selector = request.POST.get("selector", "").strip()
    env_id = request.POST.get("env_id", "").strip()
    last_html = request.session.get('relay_last_response_html')

    if not var_name or not selector:
        return JsonResponse({"error": "Both a variable name and a CSS selector are required."}, status=400)

    if last_html is None:
        return JsonResponse({"error": "No HTML response available yet — send a request first."}, status=400)

    value = extract_html_path(last_html, selector)
    if value is None:
        return JsonResponse({"error": f"Could not find anything matching '{selector}'."}, status=400)

    extracted = request.session.get('relay_extracted_vars', {})
    extracted[var_name] = value
    request.session['relay_extracted_vars'] = extracted
    request.session.modified = True

    if env_id and request.user.is_authenticated:
        env = Environment.objects.filter(owner=request.user, id=env_id).first()
        if env:
            env_vars = env.get_vars()
            env_vars[var_name] = value
            env.set_vars(env_vars)
            env.save()

    return JsonResponse({"var_name": var_name, "value": value, "extracted_vars": extracted})


@login_required
def get_environment_api(request, env_id):
    env = Environment.objects.filter(owner=request.user, id=env_id).first()
    if not env:
        return JsonResponse({"error": "Not found."}, status=404)
    return JsonResponse({"id": env.id, "name": env.name, "collection_id": env.collection_id, "vars": env.get_vars()})


@login_required
@require_POST
def update_environment_api(request, env_id):
    env = Environment.objects.filter(owner=request.user, id=env_id).first()
    if not env:
        return JsonResponse({"error": "Not found."}, status=404)
    try:
        parsed = json.loads(request.POST.get("vars_json", "{}"))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid variable data."}, status=400)
    env.set_vars(parsed)
    env.save()
    return JsonResponse({"ok": True, "id": env.id, "vars": env.get_vars()})


@login_required
@require_POST
def delete_environment_api(request, env_id):
    Environment.objects.filter(owner=request.user, id=env_id).delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def create_flow_api(request):
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Flow name is required."}, status=400)
    try:
        steps_data = json.loads(request.POST.get("steps_json", "[]"))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid steps data."}, status=400)

    flow = Flow.objects.create(owner=request.user, name=name)
    for i, s in enumerate(steps_data):
        sr = SavedRequest.objects.filter(collection__owner=request.user, id=s.get("saved_request_id")).first()
        if not sr:
            continue
        FlowStep.objects.create(
            flow=flow,
            order=i,
            saved_request=sr,
            extract_type=s.get("extract_type", "none"),
            extract_path=s.get("extract_path", ""),
            extract_var_name=s.get("extract_var_name", ""),
        )

    return render(request, "partials/flows_list.html", {
        "flows": Flow.objects.filter(owner=request.user).prefetch_related('steps__saved_request')
    })


@login_required
@require_POST
def delete_flow_api(request, flow_id):
    Flow.objects.filter(owner=request.user, id=flow_id).delete()
    return render(request, "partials/flows_list.html", {
        "flows": Flow.objects.filter(owner=request.user).prefetch_related('steps__saved_request')
    })


@login_required
def flow_detail_api(request, flow_id):
    flow = Flow.objects.filter(owner=request.user, id=flow_id).prefetch_related('steps__saved_request').first()
    if not flow:
        return JsonResponse({"error": "Not found."}, status=404)
    return JsonResponse({
        "id": flow.id,
        "name": flow.name,
        "steps": [
            {
                "id": s.id,
                "name": s.saved_request.name,
                "method": s.saved_request.method,
                "url": s.saved_request.url,
                "extract_var_name": s.extract_var_name,
                "extract_type": s.extract_type,
                "extract_path": s.extract_path,
            }
            for s in flow.steps.order_by('order', 'id')
        ]
    })


@login_required
@require_POST
def run_flow_api(request, flow_id):
    flow = Flow.objects.filter(owner=request.user, id=flow_id).prefetch_related('steps__saved_request').first()
    if not flow:
        return JsonResponse({"error": "Not found."}, status=404)

    active_env_id = request.POST.get("active_env_id", "").strip()
    env = None
    accumulated = {}
    if active_env_id:
        env = Environment.objects.filter(owner=request.user, id=active_env_id).first()
        if env:
            accumulated = env.get_vars()

    results = []
    for step in flow.steps.order_by('order', 'id'):
        sr = step.saved_request
        url = resolve_env_variables(sr.url, accumulated)
        headers_list = sr.get_headers()
        headers = {
            resolve_env_variables(h['key'], accumulated): resolve_env_variables(h['val'], accumulated)
            for h in headers_list if h.get('key')
        }
        body = resolve_env_variables(sr.body, accumulated) if sr.body else sr.body

        if body and not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = "application/json"

        auth_data = sr.get_auth_data()
        headers = apply_auth_headers(headers, sr.auth_type, auth_data)

        response_data = execute_relay_request(method=sr.method, url=url, headers=headers, body=body)

        extracted_value = None
        extracted_error = None
        if step.extract_var_name:
            raw_body = response_data.get("body", "")
            if step.extract_type == "json":
                try:
                    parsed = json.loads(raw_body)
                    extracted_value = extract_json_path(parsed, step.extract_path)
                except (ValueError, TypeError):
                    extracted_error = "Response wasn't valid JSON."
            elif step.extract_type == "html":
                extracted_value = extract_html_path(raw_body, step.extract_path)

            if extracted_value is not None:
                accumulated[step.extract_var_name] = extracted_value
            elif not extracted_error:
                extracted_error = f"Could not find '{step.extract_path}' in the response."

        results.append({
            "step_id": step.id,
            "name": sr.name,
            "method": sr.method,
            "url": url,
            "status_code": response_data.get("status_code", 0),
            "status_category": response_data.get("status_category", "server_error"),
            "elapsed_ms": response_data.get("elapsed_ms", 0),
            "extract_var_name": step.extract_var_name,
            "extracted_value": extracted_value,
            "extracted_error": extracted_error,
        })

        RequestHistory.objects.create(
            owner=request.user,
            saved_request=sr,
            method=sr.method,
            url=url,
            headers_json=json.dumps([{"key": k, "val": v} for k, v in headers.items()]),
            body=body or "",
            auth_type=sr.auth_type,
            auth_data_json=sr.auth_data_json,
            status_code=response_data.get("status_code", 0),
            status_category=response_data.get("status_category", "server_error"),
            elapsed_ms=response_data.get("elapsed_ms", 0),
        )

        if response_data.get("status_code", 0) == 0:
            break  # connection failure — stop the chain, later steps would fail anyway

    if env is not None:
        env.set_vars(accumulated)
        env.save()

    return JsonResponse({"results": results, "final_vars": accumulated})


@login_required
@require_http_methods(["POST"])
def save_assertions(request):
    """Save assertions for the current user's session or workspace"""
    try:
        data = json.loads(request.body)
        assertions = data.get('assertions', [])

        # Store assertions in session
        request.session['relay_assertions'] = assertions
        request.session.modified = True

        return JsonResponse({'ok': True, 'message': 'Assertions saved successfully'})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_assertions(request):
    """Retrieve saved assertions"""
    assertions = request.session.get('relay_assertions', [
        {'type': 'status', 'operator': 'equals', 'expected': '200', 'path': '', 'message': 'Status should be 200'},
        {'type': 'response_time', 'operator': 'less_than', 'expected': '500', 'path': '',
         'message': 'Response time < 500ms'},
    ])
    return JsonResponse({'assertions': assertions})


@login_required
@require_http_methods(["POST"])
def run_assertions(request):
    """Run assertions on a provided response data"""
    try:
        data = json.loads(request.body)
        response_data = data.get('response_data', {})
        assertions = request.session.get('relay_assertions', [])

        results = evaluate_assertions(assertions, response_data)
        return JsonResponse({'results': results})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def evaluate_assertions(assertions, response_data):
    """Evaluate assertions against response data"""
    results = []

    for assertion in assertions:
        result = evaluate_single_assertion(assertion, response_data)
        results.append(result)

    return results


def evaluate_single_assertion(assertion, response_data):
    """Evaluate a single assertion"""
    result = {
        'type': assertion.get('type', 'status'),
        'pass': False,
        'detail': '',
        'skipped': False
    }

    assertion_type = assertion.get('type', 'status')
    operator = assertion.get('operator', 'equals')
    expected = assertion.get('expected', '')
    path = assertion.get('path', '')
    message = assertion.get('message', '')

    try:
        if assertion_type == 'status':
            status_code = response_data.get('status_code', 0)
            expected_int = int(expected) if expected else 0
            passed = compare_values(status_code, operator, expected_int)
            result['pass'] = passed
            result['detail'] = f"Status: {status_code} {operator} {expected_int}"

        elif assertion_type == 'response_time':
            elapsed_ms = response_data.get('elapsed_ms', 0)
            expected_int = float(expected) if expected else 0
            passed = compare_values(elapsed_ms, operator, expected_int)
            result['pass'] = passed
            result['detail'] = f"Time: {elapsed_ms}ms {operator} {expected_int}ms"

        elif assertion_type == 'json_path':
            body = response_data.get('body', '{}')
            value = extract_json_path(body, path)

            if operator in ['exists', 'not_exists']:
                passed = (operator == 'exists') == (value is not None)
                result['pass'] = passed
                result['detail'] = f"Path {path} {operator}: {passed}"
            else:
                expected_value = parse_expected_value(expected)
                passed = compare_values(value, operator, expected_value)
                result['pass'] = passed
                result['detail'] = f"Path {path}: {value} {operator} {expected_value}"

        elif assertion_type == 'header':
            headers = response_data.get('headers', {})
            header_value = headers.get(path, '')

            if operator in ['exists', 'not_exists']:
                passed = (operator == 'exists') == (path in headers)
                result['pass'] = passed
                result['detail'] = f"Header {path} {operator}: {passed}"
            else:
                passed = compare_values(header_value, operator, expected)
                result['pass'] = passed
                result['detail'] = f"Header {path}: {header_value} {operator} {expected}"

        elif assertion_type == 'regex':
            body = response_data.get('body', '')
            try:
                regex = re.compile(path)
                passed = bool(regex.search(body))
                result['pass'] = passed
                result['detail'] = f"Regex {path} {'matched' if passed else 'did not match'}"
            except re.error as e:
                result['pass'] = False
                result['detail'] = f"Invalid regex: {str(e)}"

    except Exception as e:
        result['pass'] = False
        result['detail'] = f"Error: {str(e)}"

    if message:
        result['detail'] = f"{message} - {result['detail']}"

    return result


def compare_values(actual, operator, expected):
    """Compare values based on operator"""
    try:
        # Convert both to strings for contains operations
        if operator in ['contains', 'not_contains']:
            return str(expected).lower() in str(actual).lower()

        # For equals/not_equals, try to compare as numbers first
        if operator in ['equals', 'not_equals']:
            # If both can be numbers, compare as numbers
            try:
                actual_num = float(actual)
                expected_num = float(expected)
                if operator == 'equals':
                    return actual_num == expected_num
                else:
                    return actual_num != expected_num
            except (ValueError, TypeError):
                # Fall back to string comparison
                if operator == 'equals':
                    return str(actual) == str(expected)
                else:
                    return str(actual) != str(expected)

        # For numeric comparisons
        if operator in ['less_than', 'greater_than']:
            actual_num = float(actual)
            expected_num = float(expected)
            if operator == 'less_than':
                return actual_num < expected_num
            else:
                return actual_num > expected_num

        # For exists/not_exists
        if operator == 'exists':
            return actual is not None and actual != ''
        if operator == 'not_exists':
            return actual is None or actual == ''

        return False
    except (ValueError, TypeError) as e:
        print(f"Comparison error: {e}")
        return False


def parse_expected_value(value):
    """Parse string to appropriate type"""
    if value == 'true':
        return True
    elif value == 'false':
        return False
    elif value == 'null':
        return None
    elif value == 'undefined':
        return None
    elif value.isdigit():
        return int(value)
    elif value.replace('.', '', 1).isdigit():
        return float(value)
    else:
        return value


@login_required
@require_http_methods(["GET"])
def history_list_api(request):
    """API endpoint for history list"""
    history = RequestHistory.objects.filter(owner=request.user)[:30]

    # Render partial template
    from django.template.loader import render_to_string
    html = render_to_string('partials/history_list.html', {'history': history})
    return JsonResponse({'html': html})


@login_required
@require_http_methods(["GET"])
def list_environments_api(request):
    """API endpoint for listing environments"""
    environments = Environment.objects.filter(owner=request.user)
    data = {
        'environments': [
            {'id': e.id, 'name': e.name, 'collection_id': e.collection_id}
            for e in environments
        ]
    }
    return JsonResponse(data)
