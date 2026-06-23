"""
Netlify Function - Wrapper para o Flask app.
Usa serverless_wsgi para converter entre o formato
Netlify Function (event/context) e WSGI (Flask).
"""
import os
import sys
import json
import base64
from pathlib import Path

# ---- Configura o path para encontrar o app ----
FUNCTIONS_DIR = Path(__file__).parent
PROJECT_DIR = FUNCTIONS_DIR.parent.parent  # = raiz do projeto
sys.path.insert(0, str(PROJECT_DIR))

# ---- Seta variáveis de ambiente para o modo Netlify ----
os.environ.setdefault("NETLIFY", "true")

# ---- Importa o app Flask ----
from app import app as flask_app


def handler(event, context):
    """
    Handler da Netlify Function.
    Converte o evento da Netlify para WSGI e retorna a resposta.
    """
    try:
        # Constrói o WSGI environ a partir do evento da Netlify
        method = event.get("httpMethod", "GET")
        path = event.get("path", "/")
        query_string = event.get("queryStringParameters", {}) or {}
        headers = event.get("headers", {}) or {}
        body = event.get("body", "")
        is_base64 = event.get("isBase64Encoded", False)

        # Reconstrói query string
        qs_parts = []
        for k, v in query_string.items():
            if v is not None:
                qs_parts.append(f"{k}={v}")
        qs = "&".join(qs_parts)

        # Decodifica body se base64
        if is_base64 and body:
            body = base64.b64decode(body).decode("utf-8")

        # Cria environ para o WSGI
        environ = {
            "REQUEST_METHOD": method.upper(),
            "PATH_INFO": path,
            "QUERY_STRING": qs,
            "SERVER_NAME": "netlify",
            "SERVER_PORT": "443",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "https",
            "wsgi.input": type("BytesIO", (), {"read": lambda s: body.encode("utf-8"), "readline": lambda s: ""}),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }

        # Headers
        for key, value in headers.items():
            wsgi_key = f"HTTP_{key.upper().replace('-', '_')}"
            environ[wsgi_key] = value

        # Content-Type e Content-Length
        if "content-type" in headers:
            environ["CONTENT_TYPE"] = headers["content-type"]
        if "content-length" in headers:
            environ["CONTENT_LENGTH"] = headers["content-length"]

        # Captura a resposta do Flask
        response_data = {}
        def start_response(status, response_headers, exc_info=None):
            response_data["status"] = int(status.split(" ")[0])
            response_data["headers"] = dict(response_headers)

        result = flask_app.wsgi_app(environ, start_response)
        body_bytes = b"".join(result) if isinstance(result, (list, tuple)) else result

        status = response_data.get("status", 200)
        response_headers = response_data.get("headers", {})

        # Converte body para base64 se for binário
        output = body_bytes.decode("utf-8") if isinstance(body_bytes, bytes) else body_bytes
        is_base64 = False
        response_type = response_headers.get("Content-Type", response_headers.get("content-type", ""))
        if "application" in response_type or "octet" in response_type:
            output = base64.b64encode(body_bytes).decode("utf-8") if isinstance(body_bytes, bytes) else base64.b64encode(output.encode()).decode()
            is_base64 = True

        return {
            "statusCode": status,
            "headers": response_headers,
            "body": output,
            "isBase64Encoded": is_base64,
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"erro": str(e)}),
            "isBase64Encoded": False,
        }
