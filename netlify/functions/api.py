"""
Netlify Function - Wrapper para o Flask app.
Usa serverless_wsgi para converter o evento Netlify → WSGI.
"""
import os
import sys
import json
import traceback
from pathlib import Path

# ---- Configura o path para encontrar o app ----
FUNCTIONS_DIR = Path(__file__).parent
PROJECT_DIR = FUNCTIONS_DIR.parent.parent  # = raiz do projeto
sys.path.insert(0, str(PROJECT_DIR))

# ---- Seta variáveis de ambiente para o modo Netlify ----
os.environ.setdefault("NETLIFY", "true")

# ---- Importa o app Flask ----
try:
    from app import app as flask_app
except Exception as e:
    # Se falhar, registra o erro e cria um app dummy que retorna o erro
    tb = traceback.format_exc()
    print(f"[api.py] ERRO ao importar app: {e}\n{tb}", file=sys.stderr)
    from flask import Flask
    flask_app = Flask(__name__)

    @flask_app.route("/")
    @flask_app.route("/<path:path>")
    def erro_handler(path="/"):
        return {"erro": f"Falha ao carregar a aplicação: {e}", "detalhe": tb}, 500


# ---- Handler da Netlify Function ----
def handler(event, context):
    """
    Handler da Netlify Function usando serverless-wsgi.
    """
    try:
        from serverless_wsgi import handle_request
        return handle_request(flask_app, event, context)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[api.py] ERRO no handler: {e}\n{tb}", file=sys.stderr)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"erro": str(e), "detalhe": tb}),
            "isBase64Encoded": False,
        }
