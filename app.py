"""
Gerenciador de Planilhas - Web App
====================================
Gerencia e organiza todas as planilhas em um só lugar,
com upload, visualização, busca e categorização.

Uso:
    python app.py
    # Depois abra http://localhost:5000
"""

import os
import io
import json
import math
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from flask import (
    Flask, render_template, request, jsonify,
    send_file, abort
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
METADATA_FILE = BASE_DIR / "metadata.json"

ALLOWED_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".csv", ".ods"}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

# Detecta se estamos no Netlify (variáveis de ambiente)
IS_NETLIFY = bool(os.getenv("SUPABASE_URL")) or os.getenv("NETLIFY", "").lower() == "true"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

# Backend de armazenamento
storage_backend = None
if IS_NETLIFY:
    logger.info("🔵 Modo Netlify + Supabase")
    import supabase_client as storage_backend
else:
    logger.info("🟢 Modo Local (arquivos + JSON)")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # Tenta importar supabase_client (pode não estar instalado localmente)
    try:
        import supabase_client as storage_backend
    except ImportError:
        logger.info("   (supabase_client não disponível, usando apenas modo local)")

# ---------------------------------------------------------------------------
# Metadados (JSON-based storage)
# ---------------------------------------------------------------------------


def _carregar_metadados():
    if IS_NETLIFY:
        return {}
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def _salvar_metadados(metadados):
    if IS_NETLIFY:
        return
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadados, f, ensure_ascii=False, indent=2)

def _id_arquivo(caminho):
    return hashlib.md5(str(caminho).encode()).hexdigest()[:12]

def _info_planilha(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    ext = caminho.suffix.lower()
    info = {
        "nome": caminho.name, "caminho": str(caminho),
        "tamanho": caminho.stat().st_size,
        "tamanho_formatado": _formatar_tamanho(caminho.stat().st_size),
        "extensao": ext,
        "ultima_modificacao": datetime.fromtimestamp(caminho.stat().st_mtime).isoformat(),
        "abas": [],
    }
    try:
        if ext == ".csv":
            df = pd.read_csv(caminho, nrows=100)
            info["abas"].append({
                "nome": "Sheet1", "linhas": len(df) + 1,
                "colunas": len(df.columns), "colunas_nomes": list(df.columns),
            })
        else:
            xl = pd.ExcelFile(caminho)
            for sheet in xl.sheet_names:
                df = xl.parse(sheet, nrows=100)
                info["abas"].append({
                    "nome": sheet, "linhas": len(df) + 1,
                    "colunas": len(df.columns), "colunas_nomes": list(df.columns),
                })
    except Exception as e:
        info["erro"] = str(e)
    return info

def _formatar_tamanho(bytes_val):
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"

def _allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

# =============================================================================
# HELPERS JSON
# =============================================================================

def _valor_json(val):
    if val is None:
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        if pd.isna(val):
            return None
        return val.isoformat()
    if isinstance(val, pd.Timedelta):
        if pd.isna(val):
            return None
        return str(val)
    if isinstance(val, pd.Period):
        return str(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, (np.ndarray,)):
        return val.tolist()
    try:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val

def _df_para_lista(df):
    linhas = []
    for _, row in df.iterrows():
        linhas.append([_valor_json(v) for v in row])
    return linhas


# ---------------------------------------------------------------------------
# Rotas - Páginas
# ---------------------------------------------------------------------------


# =============================================================================
# BACKEND UNIFICADO (Local ou Supabase)
# =============================================================================

def _get_planilhas():
    if IS_NETLIFY and storage_backend:
        return storage_backend.listar_planilhas()
    metadados = _carregar_metadados()
    resultado = []
    for pid, meta in metadados.items():
        caminho = Path(meta.get("caminho", ""))
        resultado.append({
            "id": pid, "nome": meta.get("nome", "?"),
            "tamanho_formatado": meta.get("tamanho_formatado", "?"),
            "ultima_modificacao": meta.get("ultima_modificacao", ""),
            "tags": meta.get("tags", []),
            "categoria": meta.get("categoria", ""),
            "descricao": meta.get("descricao", ""),
            "favorito": meta.get("favorito", False),
            "existe": caminho.exists(),
            "abas": meta.get("abas", []),
        })
    resultado.sort(key=lambda x: (not x["favorito"], x["nome"].lower()))
    return resultado

def _get_planilha(pid):
    if IS_NETLIFY and storage_backend:
        return storage_backend.obter_planilha(pid)
    metadados = _carregar_metadados()
    return metadados.get(pid)

def _update_planilha(pid, data):
    if IS_NETLIFY and storage_backend:
        return storage_backend.atualizar_planilha(pid, data)
    metadados = _carregar_metadados()
    if pid in metadados:
        metadados[pid].update(data)
        _salvar_metadados(metadados)

def _delete_planilha(pid):
    if IS_NETLIFY and storage_backend:
        return storage_backend.deletar_planilha(pid)
    metadados = _carregar_metadados()
    meta = metadados.pop(pid, None)
    if meta:
        caminho = Path(meta.get("caminho", ""))
        if caminho.exists():
            caminho.unlink()
        _salvar_metadados(metadados)


# =============================================================================
# ROTAS - Página principal
# =============================================================================

@app.route("/")
def index():
    planilhas = _get_planilhas()
    total_tags = set()
    for p in planilhas:
        for t in p.get("tags", []):
            if t:
                total_tags.add(t)
    return render_template(
        "index.html",
        title="Gerenciador de Planilhas",
        total_planilhas=len(planilhas),
        total_tags=len(total_tags),
    )


# =============================================================================
# API - Listar / Detalhes
# =============================================================================

@app.route("/api/planilhas")
def api_listar():
    return jsonify(_get_planilhas())

@app.route("/api/planilhas/<planilha_id>")
def api_detalhes(planilha_id):
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404
    return jsonify(meta)


# =============================================================================
# API - Upload
# =============================================================================

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "files" not in request.files:
        return jsonify({"erro": "Nenhum arquivo enviado"}), 400

    files = request.files.getlist("files")
    resultados = []

    for file in files:
        if file.filename == "" or not _allowed_file(file.filename):
            continue

        filename = secure_filename(file.filename)
        dados_bytes = file.read()

        if IS_NETLIFY and storage_backend:
            try:
                storage_path = storage_backend.upload_arquivo(filename, dados_bytes)
                abas, _ = storage_backend.extrair_info_planilha(dados_bytes, filename)
                meta = storage_backend.criar_planilha(
                    nome=filename, storage_path=storage_path,
                    tamanho=len(dados_bytes), extensao=Path(filename).suffix.lower(),
                    abas=abas,
                )
                resultados.append({"id": meta.get("id", ""), "nome": filename, "status": "ok"})
            except Exception as e:
                logger.error(f"Upload error: {e}")
                resultados.append({"nome": filename, "status": "erro", "mensagem": str(e)})
        else:
            final_path = UPLOAD_FOLDER / filename
            if final_path.exists():
                stem, suffix = final_path.stem, final_path.suffix
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{stem}_{ts}{suffix}"
                final_path = UPLOAD_FOLDER / filename
            with open(final_path, "wb") as f:
                f.write(dados_bytes)

            info = _info_planilha(final_path)
            if info:
                pid = _id_arquivo(final_path)
                info.update({
                    "id": pid, "tags": [], "categoria": "", "descricao": "",
                    "favorito": False, "data_upload": datetime.now().isoformat(),
                })
                metadados = _carregar_metadados()
                metadados[pid] = info
                _salvar_metadados(metadados)
                resultados.append({"id": pid, "nome": filename, "status": "ok"})
            else:
                resultados.append({"nome": filename, "status": "erro", "mensagem": "Não foi possível ler"})

    return jsonify({"resultados": resultados, "total": len(resultados)})


# =============================================================================
# API - Delete / Update
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/delete", methods=["DELETE"])
def api_deletar(planilha_id):
    if IS_NETLIFY and storage_backend:
        ok = storage_backend.deletar_planilha(planilha_id)
        if not ok:
            return jsonify({"erro": "Planilha não encontrada"}), 404
    else:
        _delete_planilha(planilha_id)
    return jsonify({"status": "ok"})

@app.route("/api/planilhas/<planilha_id>/update", methods=["PUT"])
def api_atualizar(planilha_id):
    data = request.json or {}
    _update_planilha(planilha_id, data)
    return jsonify({"status": "ok"})


# =============================================================================
# API - Download
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/download")
def api_download(planilha_id):
    meta = _get_planilha(planilha_id)
    if not meta:
        abort(404)

    if IS_NETLIFY and storage_backend:
        storage_path = meta.get("storage_path", "")
        if not storage_path:
            abort(404)
        dados_bytes = storage_backend.download_arquivo(storage_path)
        return send_file(io.BytesIO(dados_bytes), as_attachment=True, download_name=meta["nome"])
    else:
        caminho = Path(meta.get("caminho", ""))
        if not caminho.exists():
            abort(404)
        return send_file(str(caminho), as_attachment=True)


# =============================================================================
# API - Preview
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/preview")
def api_preview(planilha_id):
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404

    sheet = request.args.get("sheet", "")
    limite = min(int(request.args.get("limite", 50)), 200)
    ext = Path(meta["nome"]).suffix.lower()

    try:
        if IS_NETLIFY and storage_backend:
            storage_path = meta.get("storage_path", "")
            if not storage_path:
                return jsonify({"erro": "Arquivo não encontrado"}), 404
            dados_bytes = storage_backend.download_arquivo(storage_path)
            stream = io.BytesIO(dados_bytes)
        else:
            caminho = Path(meta.get("caminho", ""))
            if not caminho.exists():
                return jsonify({"erro": "Arquivo não encontrado"}), 404
            stream = str(caminho)

        if ext == ".csv":
            df = pd.read_csv(stream, nrows=limite)
            dados = {"abas": [{"nome": "Sheet1", "colunas": list(df.columns), "linhas": _df_para_lista(df), "total_linhas": len(df)}]}
        else:
            xl = pd.ExcelFile(stream)
            abas = []
            for s in xl.sheet_names:
                if sheet and s != sheet:
                    continue
                df = xl.parse(s, nrows=limite)
                abas.append({"nome": s, "colunas": list(df.columns), "linhas": _df_para_lista(df), "total_linhas": len(df)})
            dados = {"abas": abas}

        return jsonify(dados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# API - Tags / Categorias
# =============================================================================

@app.route("/api/tags")
def api_listar_tags():
    if IS_NETLIFY and storage_backend:
        return jsonify(storage_backend.listar_tags_categorias())
    metadados = _carregar_metadados()
    todas_tags = set()
    categorias = set()
    for meta in metadados.values():
        for tag in meta.get("tags", []):
            if tag:
                todas_tags.add(tag)
        if meta.get("categoria"):
            categorias.add(meta["categoria"])
    return jsonify({"tags": sorted(todas_tags), "categorias": sorted(categorias)})


# =============================================================================
# API - Estatísticas
# =============================================================================

def _parse_size(size_str):
    size_str = str(size_str).strip()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            try:
                return float(size_str.replace(unit, "").strip()) * multiplier
            except ValueError:
                pass
    return 0

@app.route("/api/stats")
def api_stats():
    planilhas = _get_planilhas()
    total = len(planilhas)
    total_tamanho = 0
    ext_counts = {}
    tag_counts = {}
    categoria_counts = {}
    favoritos = 0
    recentes = 0
    limite_recente = datetime.now() - timedelta(days=7)

    for p in planilhas:
        total_tamanho += _parse_size(p.get("tamanho_formatado", "0 B"))
        ext = Path(p.get("nome", "")).suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        for tag in p.get("tags", []):
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        cat = p.get("categoria", "")
        if cat:
            categoria_counts[cat] = categoria_counts.get(cat, 0) + 1
        if p.get("favorito"):
            favoritos += 1
        mod = p.get("ultima_modificacao", "")
        if mod:
            try:
                if datetime.fromisoformat(mod) >= limite_recente:
                    recentes += 1
            except ValueError:
                pass

    return jsonify({
        "total_planilhas": total,
        "total_tamanho": total_tamanho,
        "total_tamanho_formatado": _formatar_tamanho(total_tamanho),
        "extensoes": dict(sorted(ext_counts.items())),
        "tags_mais_usadas": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10]),
        "categorias": dict(sorted(categoria_counts.items())),
        "total_tags": len(tag_counts),
        "favoritos": favoritos,
        "recentes_7dias": recentes,
    })
# =============================================================================
# API - Busca
# =============================================================================

@app.route("/api/buscar")
def api_buscar():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    planilhas = _get_planilhas()
    resultados = []
    for p in planilhas:
        score = 0
        if q in p.get("nome", "").lower():
            score += 10
        for tag in p.get("tags", []):
            if q in tag.lower():
                score += 5

        if q in p.get("categoria", "").lower():
            score += 3
        if q in p.get("descricao", "").lower():
            score += 2
        if score > 0:
            resultados.append({
                "id": p["id"], "nome": p.get("nome", ""),
                "tamanho_formatado": p.get("tamanho_formatado", ""),
                "tags": p.get("tags", []), "categoria": p.get("categoria", ""),
                "score": score,
            })
    resultados.sort(key=lambda x: -x["score"])
    return jsonify(resultados[:30])


# =============================================================================
# API - Scan (apenas local)
# =============================================================================

@app.route("/api/scan")
def api_scan():
    if IS_NETLIFY:
        return jsonify({"adicionados": 0, "total": len(_get_planilhas())})
    metadados = _carregar_metadados()
    adicionados = 0
    for arquivo in UPLOAD_FOLDER.iterdir():
        if not arquivo.is_file() or arquivo.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        pid = _id_arquivo(arquivo)
        if pid not in metadados:
            info = _info_planilha(arquivo)
            if info:
                info.update({
                    "id": pid, "tags": [], "categoria": "", "descricao": "",
                    "favorito": False, "data_upload": datetime.now().isoformat(),
                })
                metadados[pid] = info
                adicionados += 1
    _salvar_metadados(metadados)
    return jsonify({"adicionados": adicionados, "total": len(metadados)})


# =============================================================================
# INICIALIZAÇÃO
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  📊 Gerenciador de Planilhas")
    print(f"  Modo: {'Netlify + Supabase' if IS_NETLIFY else 'Local (arquivos)'}")
    print("  Abra http://localhost:5000 no navegador")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
