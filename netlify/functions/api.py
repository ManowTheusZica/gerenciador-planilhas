"""
Netlify Function - Wrapper para o Flask app.
Converte o evento da Netlify (API Gateway) para WSGI e vice-versa.
"""
import os
import sys
import io
import json
import base64
import traceback
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
    Converte o evento Netlify → WSGI → Flask → resposta.
    """
    try:
        # --- Extrai dados do evento ---
        method = event.get("httpMethod", "GET")
        path = event.get("path", "/")
        raw_query = event.get("rawQuery", "") or ""
        query_params = event.get("queryStringParameters") or {}
        headers = event.get("headers") or {}
        body = event.get("body") or ""
        is_b64 = event.get("isBase64Encoded", False)

        # Reconstrói query string a partir dos parâmetros (se rawQuery vazio)
        qs = raw_query
        if not qs and query_params:
            qs = "&".join(f"{k}={v}" for k, v in query_params.items() if v is not None)

        # Decodifica body base64 → bytes
        raw_body: bytes = b""
        if body:
            raw_body = base64.b64decode(body) if is_b64 else body.encode("utf-8")

        # --- Monta o WSGI environ ---
        environ = {
            "REQUEST_METHOD": method.upper(),
            "PATH_INFO": path,
            "QUERY_STRING": qs,
            "SCRIPT_NAME": "",
            "SERVER_NAME": "netlify",
            "SERVER_PORT": "443",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "https",
            "wsgi.input": io.BytesIO(raw_body),
            "wsgi.errors": io.StringIO(),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }

        # Headers HTTP → WSGI
        for key, value in headers.items():
            if key.lower() == "content-type":
                environ["CONTENT_TYPE"] = value
            elif key.lower() == "content-length":
                environ["CONTENT_LENGTH"] = str(value)
            else:
                wsgi_key = f"HTTP_{key.upper().replace('-', '_')}"
                environ[wsgi_key] = value

        if not environ.get("CONTENT_LENGTH") and raw_body:
            environ["CONTENT_LENGTH"] = str(len(raw_body))

        # --- Processa com Flask ---
        response_data = {"status": 200, "headers": [], "body": b""}

        def start_response(status, response_headers, exc_info=None):
            response_data["status"] = int(status.split(" ")[0])
            response_data["headers"] = list(response_headers)

        result = flask_app.wsgi_app(environ, start_response)

        # Junta o body (pode ser iterável de bytes ou strings)
        body_chunks = []
        for chunk in result:
            if isinstance(chunk, str):
                body_chunks.append(chunk.encode("utf-8"))
            else:
                body_chunks.append(chunk)
        response_data["body"] = b"".join(body_chunks) if body_chunks else b""

        # --- Converte a resposta para o formato Netlify ---
        status = response_data["status"]
        response_headers = {}
        has_binary = False
        for key, value in response_data["headers"]:
            # Agrupa headers com mesmo nome (ex: Set-Cookie)
            if key in response_headers:
                response_headers[key] = f"{response_headers[key]}, {value}"
            else:
                response_headers[key] = value
            if key.lower() == "content-type":
                ct = value.lower()
                if "application" in ct or "octet" in ct or "image" in ct:
                    has_binary = True

        body_bytes = response_data["body"]

        # Se for binário, codifica em base64
        if has_binary and body_bytes:
            output = base64.b64encode(body_bytes).decode("utf-8")
            return {
                "statusCode": status,
                "headers": response_headers,
                "body": output,
                "isBase64Encoded": True,
            }
        else:
            output = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
            return {
                "statusCode": status,
                "headers": response_headers,
                "body": output,
                "isBase64Encoded": False,
            }

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[api.py ERROR] {e}\n{tb}", file=sys.stderr)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"erro": str(e), "detalhe": tb}),
            "isBase64Encoded": False,
        }
