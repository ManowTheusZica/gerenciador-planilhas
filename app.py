"""
Gerenciador de Planilhas - Web App v2.0
====================================
Gerencia e organiza todas as planilhas em um só lugar,
com upload, visualização, busca e categorização.

Versão 2.0: Correção do schema Supabase (tabela planilhas criada)

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
import threading
import mimetypes
from collections import defaultdict  # type: ignore[unused-import]
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from flask import (
    Flask, render_template, request, jsonify,
    send_file, abort
)
from typing import Any, Dict, List, Optional
from flask_socketio import SocketIO, emit, join_room, leave_room  # type: ignore[attr-defined]
from werkzeug.utils import secure_filename

# Mapeamento de extensões para MIME types válidos
VALID_MIME_TYPES = {
    ".xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",  # Excel às vezes é detectado como zip
        "application/octet-stream"
    ],
    ".xls": ["application/vnd.ms-excel", "application/octet-stream"],
    ".xlsm": [
        "application/vnd.ms-excel.sheet.macroEnabled.12",
        "application/octet-stream"
    ],
    ".csv": ["text/csv", "application/csv", "text/plain", "application/octet-stream"],
    ".ods": [
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/zip",
        "application/octet-stream"
    ],
}

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

# ---------------------------------------------------------------------------
# Socket.IO (colaboração em tempo real)
# ---------------------------------------------------------------------------
socketio = SocketIO(app, cors_allowed_origins="*")

# Cache de planilhas abertas para edição colaborativa
# planilha_cache: {planilha_id: {meta: {...}, sheets: {sheet_name: {colunas: [...], linhas: [[...]]}}}}
planilha_cache: Dict[str, Dict[str, Any]] = {}
cache_lock = threading.Lock()

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

# Backend de armazenamento
import supabase_client as _supabase_module  # type: ignore
storage_backend: Any = None

# Verifica se o Supabase está realmente configurado (variáveis de ambiente presentes)
supabase_configurado = bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_SERVICE_KEY"))

if IS_NETLIFY and supabase_configurado:
    logger.info("🔵 Modo Netlify + Supabase")
    storage_backend = _supabase_module
else:
    if IS_NETLIFY and not supabase_configurado:
        logger.warning("⚠️  NETLIFY=true mas Supabase não configurado. Usando modo local.")
        logger.warning("   Configure SUPABASE_URL e SUPABASE_SERVICE_KEY nas variáveis de ambiente do Render")
    logger.info("🟢 Modo Local (arquivos + JSON)")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # Tenta importar supabase_client (pode não estar instalado localmente)
    try:
        storage_backend = _supabase_module
    except ImportError:
        logger.info("   (supabase_client não disponível, usando apenas modo local)")

# ---------------------------------------------------------------------------
# SISTEMA DE BACKUP E VERSIONAMENTO
# ---------------------------------------------------------------------------

BACKUP_DIR = BASE_DIR / "backups"
VERSIONS_DIR = BASE_DIR / "versions"
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(VERSIONS_DIR, exist_ok=True)


def _criar_backup_local(caminho_arquivo: str) -> None:
    """Cria backup de um arquivo local antes de modificá-lo."""
    try:
        caminho_p = Path(caminho_arquivo)
        if not caminho_p.exists():
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_nome = f"{caminho_p.stem}_backup_{timestamp}{caminho_p.suffix}"
        backup_path = BACKUP_DIR / backup_nome
        
        import shutil
        shutil.copy2(str(caminho_p), str(backup_path))
        logger.info(f"Backup criado: {backup_path}")
        
        # Limpa backups antigos (>10)
        backups = sorted(BACKUP_DIR.glob(f"{caminho_p.stem}_backup_*"))
        if len(backups) > 10:
            for backup_antigo in backups[:-10]:
                backup_antigo.unlink()
    except Exception as e:
        logger.error(f"Erro ao criar backup: {e}")


def _criar_backup_versionamento(planilha_id: str, motivo: str = "manual") -> None:
    """Cria versão snapshot da planilha antes de modificações."""
    try:
        meta = _get_planilha(planilha_id)
        if not meta:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        versao_dir = VERSIONS_DIR / planilha_id
        os.makedirs(versao_dir, exist_ok=True)
        
        versao_info = {
            "version_id": f"{planilha_id}_{timestamp}",
            "planilha_id": planilha_id,
            "nome": meta.get("nome", ""),
            "motivo": motivo,
            "data": datetime.now().isoformat(),
            "tamanho": meta.get("tamanho", 0),
            "metadata_snapshot": meta,
        }
        
        # Salva metadados da versão
        versao_file = versao_dir / f"v_{timestamp}.json"
        with open(versao_file, 'w', encoding='utf-8') as f:
            json.dump(versao_info, f, ensure_ascii=False, indent=2)
        
        # Se modo local, copia arquivo físico
        if not _supabase_disponivel():
            caminho = Path(meta.get("caminho", ""))
            if caminho.exists():
                import shutil
                arquivo_versao = versao_dir / f"v_{timestamp}{caminho.suffix}"
                shutil.copy2(str(caminho), str(arquivo_versao))
        
        logger.info(f"Versão criada: {versao_info['version_id']} ({motivo})")
        
        # Mantém apenas últimas 20 versões
        versoes = sorted(versao_dir.glob("v_*.json"))
        if len(versoes) > 20:
            for versao_antiga in versoes[:-20]:
                versao_antiga.unlink()
                # Remove arquivo correspondente se existir
                arquivo_corr = versao_antiga.with_suffix(Path(meta.get("nome", "")).suffix if meta else ".xlsx")
                if arquivo_corr.exists():
                    arquivo_corr.unlink()
                    
    except Exception as e:
        logger.error(f"Erro ao criar versionamento: {e}")


# ---------------------------------------------------------------------------
# SISTEMA DE NOTIFICAÇÕES
# ---------------------------------------------------------------------------

NOTIFICACOES_FILE = BASE_DIR / "notificacoes.json"
notificacoes_cache: List[Dict[str, Any]] = []


def _carregar_notificacoes() -> List[Dict[str, Any]]:
    """Carrega notificações do arquivo."""
    global notificacoes_cache
    if NOTIFICACOES_FILE.exists():
        try:
            with open(NOTIFICACOES_FILE, 'r', encoding='utf-8') as f:
                notificacoes_cache = json.load(f)
        except Exception:
            notificacoes_cache = []
    return notificacoes_cache


def _salvar_notificacao(tipo: str, mensagem: str, dados: Optional[Dict] = None) -> None:
    """Salva uma nova notificação."""
    notificacao = {
        "id": hashlib.md5(f"{datetime.now().isoformat()}{mensagem}".encode()).hexdigest()[:12],
        "tipo": tipo,  # upload, delete, update, error, warning
        "mensagem": mensagem,
        "dados": dados or {},
        "data": datetime.now().isoformat(),
        "lida": False,
    }
    
    notificacoes = _carregar_notificacoes()
    notificacoes.insert(0, notificacao)
    
    # Mantém apenas últimas 100 notificações
    notificacoes = notificacoes[:100]
    
    with open(NOTIFICACOES_FILE, 'w', encoding='utf-8') as f:
        json.dump(notificacoes, f, ensure_ascii=False, indent=2)
    
    notificacoes_cache = notificacoes
    
    # Emite via Socket.IO se houver clientes conectados
    socketio.emit('nova_notificacao', notificacao)


def _notificar_usuarios(evento: str, dados: Dict[str, Any]) -> None:
    """Notifica usuários sobre eventos importantes."""
    mensagens = {
        "upload": f"Nova planilha enviada: {dados.get('nome', '')}",
        "delete": f"Planilha removida: {dados.get('nome', '')}",
        "update": f"Planilha atualizada: {dados.get('nome', '')}",
        "error": f"Erro: {dados.get('erro', 'Desconhecido')}",
    }
    
    mensagem = mensagens.get(evento, f"Evento: {evento}")
    _salvar_notificacao(evento, mensagem, dados)
    logger.info(f"Notificação: {mensagem}")


# ---------------------------------------------------------------------------
# Metadados (JSON-based storage)
# ---------------------------------------------------------------------------


def _carregar_metadados() -> Dict[str, Any]:
    if IS_NETLIFY:
        return {}
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def _salvar_metadados(metadados: Dict[str, Any]) -> None:
    if IS_NETLIFY:
        return
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadados, f, ensure_ascii=False, indent=2)

def _id_arquivo(caminho: str) -> str:
    return hashlib.md5(str(caminho).encode()).hexdigest()[:12]

def _info_planilha(caminho: str) -> Optional[Dict[str, Any]]:
    caminho_p = Path(caminho)
    if not caminho_p.exists():
        return None
    ext = caminho_p.suffix.lower()
    info: Dict[str, Any] = {
        "nome": caminho_p.name, "caminho": str(caminho_p),
        "tamanho": caminho_p.stat().st_size,
        "tamanho_formatado": _formatar_tamanho(caminho_p.stat().st_size),
        "extensao": ext,
        "ultima_modificacao": datetime.fromtimestamp(caminho_p.stat().st_mtime).isoformat(),
        "abas": [],
    }
    try:
        if ext == ".csv":
            df = pd.read_csv(caminho_p, nrows=100)
            info["abas"].append({
                "nome": "Sheet1", "linhas": len(df) + 1,
                "colunas": len(df.columns), "colunas_nomes": list(df.columns),
            })
        else:
            xl = pd.ExcelFile(caminho_p)
            for sheet in xl.sheet_names:
                df = xl.parse(sheet, nrows=100)
                info["abas"].append({
                    "nome": sheet, "linhas": len(df) + 1,
                    "colunas": len(df.columns), "colunas_nomes": list(df.columns),
                })
    except Exception as e:
        info["erro"] = str(e)
    return info

def _formatar_tamanho(bytes_val: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"

def _allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _validar_mime_type(dados_bytes: bytes, filename: str) -> tuple[bool, str]:
    """
    Valida o tipo MIME real do arquivo além da extensão.
    Retorna (válido, mensagem_erro).
    """
    ext = Path(filename).suffix.lower()
    
    # Detecta MIME type dos primeiros bytes
    mime_type, _ = mimetypes.guess_type(filename)
    
    # Se não conseguiu detectar pela extensão, tenta magic bytes
    if not mime_type or mime_type == "application/octet-stream":
        # Verifica magic bytes para Excel (ZIP-based)
        if dados_bytes[:4] == b'PK\x03\x04':  # ZIP signature
            if ext in ['.xlsx', '.xlsm', '.ods']:
                return True, ""
        elif dados_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':  # OLE2 (old Excel)
            if ext == '.xls':
                return True, ""
        elif ext == '.csv':
            # CSV é texto, verifica se parece texto
            try:
                dados_bytes[:1024].decode('utf-8')
                return True, ""
            except UnicodeDecodeError:
                try:
                    dados_bytes[:1024].decode('latin-1')
                    return True, ""
                except UnicodeDecodeError:
                    return False, "Arquivo CSV inválido ou corrompido"
    
    # Verifica se o MIME type detectado está na lista de válidos
    mime_types_validos = VALID_MIME_TYPES.get(ext, [])
    if mime_type in mime_types_validos or not mime_types_validos:
        return True, ""
    
    return False, f"Tipo de arquivo inválido: {mime_type} (esperado: {', '.join(mime_types_validos)})"


# =============================================================================
# HELPERS JSON
# =============================================================================

def _valor_json(val: Any) -> Any:
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
        return int(val)  # type: ignore[arg-type]
    if isinstance(val, (np.floating,)):
        if np.isnan(val) or np.isinf(val):  # type: ignore[arg-type]
            return None
        return float(val)  # type: ignore[arg-type]
    if isinstance(val, np.bool_):
        return bool(val)  # type: ignore[arg-type]
    if isinstance(val, (np.ndarray,)):
        return val.tolist()
    try:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val

def _df_para_lista(df: pd.DataFrame) -> List[List[Any]]:
    linhas: List[List[Any]] = []
    for _, row in df.iterrows():
        linhas.append([_valor_json(v) for v in row])
    return linhas


# ---------------------------------------------------------------------------
# Rotas - Páginas
# ---------------------------------------------------------------------------


# =============================================================================
# BACKEND UNIFICADO (Local ou Supabase)
# =============================================================================

supabase_erro: str = ""  # Guarda mensagem de erro do Supabase, se houver

def _supabase_disponivel() -> bool:
    """Verifica se o Supabase está configurado e acessível."""
    global supabase_erro
    if not IS_NETLIFY or not storage_backend:
        return False
    try:
        if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
            supabase_erro = "Supabase não configurado. Defina SUPABASE_URL e SUPABASE_SERVICE_KEY nas variáveis de ambiente."
            return False
        return True
    except Exception as e:
        supabase_erro = str(e)
        return False

def _get_planilhas() -> List[Dict[str, Any]]:
    if _supabase_disponivel():
        try:
            return storage_backend.listar_planilhas()  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Supabase list error: {e}")
            return []
    metadados = _carregar_metadados()
    resultado: List[Dict[str, Any]] = []
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

def _get_planilha(pid: str) -> Optional[Dict[str, Any]]:
    if _supabase_disponivel():
        try:
            return storage_backend.obter_planilha(pid)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Supabase get error: {e}")
            return None
    metadados = _carregar_metadados()
    return metadados.get(pid)

def _update_planilha(pid: str, data: Dict[str, Any]) -> None:
    if _supabase_disponivel():
        try:
            storage_backend.atualizar_planilha(pid, data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Supabase update error: {e}")
        return
    metadados = _carregar_metadados()
    if pid in metadados:
        metadados[pid].update(data)
        _salvar_metadados(metadados)

def _delete_planilha(pid: str) -> None:
    if _supabase_disponivel():
        try:
            storage_backend.deletar_planilha(pid)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Supabase delete error: {e}")
        return
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
    total_tags: set[str] = set()
    for p in planilhas:
        for t in p.get("tags", []):
            if t:
                total_tags.add(t)
    return render_template(
        "index.html",
        title="Gerenciador de Planilhas",
        total_planilhas=len(planilhas),
        total_tags=len(total_tags),
        supabase_erro=supabase_erro,
    )


# =============================================================================
# API - Listar / Detalhes
# =============================================================================

@app.route("/api/planilhas")
def api_listar():
    return jsonify(_get_planilhas())

@app.route("/api/planilhas/<planilha_id>")
def api_detalhes(planilha_id: str):
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
    resultados: List[Dict[str, Any]] = []

    for file in files:
        if not file.filename or not _allowed_file(file.filename):
            continue

        filename = secure_filename(file.filename or "arquivo")
        dados_bytes: bytes = file.read()
        
        # Validação MIME type
        valido, erro_mime = _validar_mime_type(dados_bytes, filename)
        if not valido:
            logger.warning(f"Upload rejeitado (MIME inválido): {filename} - {erro_mime}")
            resultados.append({"nome": filename, "status": "erro", "mensagem": erro_mime})
            continue
        
        # Verificação de tamanho mínimo (evita arquivos vazios)
        if len(dados_bytes) < 10:
            resultados.append({"nome": filename, "status": "erro", "mensagem": "Arquivo muito pequeno ou vazio"})
            continue

        if _supabase_disponivel():
            try:
                # Verifica se já existe planilha com mesmo nome
                existente = storage_backend.obter_planilha_por_nome(filename)  # type: ignore[union-attr]
                substituir = request.args.get("replace", "").lower() == "true"
                
                if existente and (substituir or request.args.get("force") == "true"):
                    # Criar backup antes de substituir
                    _criar_backup_versionamento(existente["id"], "substituicao_upload")
                    
                    # Substituir arquivo existente
                    storage_backend.deletar_arquivo_storage(existente.get("storage_path", ""))
                    storage_path = storage_backend.upload_arquivo(filename, dados_bytes)
                    abas, _ = storage_backend.extrair_info_planilha(dados_bytes, filename)
                    storage_backend.atualizar_planilha(existente["id"], {
                        "storage_path": storage_path,
                        "tamanho": len(dados_bytes),
                        "tamanho_formatado": _formatar_tamanho(len(dados_bytes)),
                        "ultima_modificacao": datetime.now().isoformat(),
                        "abas": json.dumps(abas, ensure_ascii=False),
                    })
                    _notificar_usuarios("upload", {"acao": "substituido", "nome": filename})
                    resultados.append({"id": existente["id"], "nome": filename, "status": "ok", "substituido": True})
                elif existente and not substituir:
                    # Nome duplicado, avisa
                    resultados.append({"id": existente["id"], "nome": filename, "status": "duplicado", "mensagem": "Já existe uma planilha com este nome. Use ?replace=true para substituir."})
                else:
                    # Novo arquivo
                    storage_path = storage_backend.upload_arquivo(filename, dados_bytes)
                    abas, _ = storage_backend.extrair_info_planilha(dados_bytes, filename)
                    meta = storage_backend.criar_planilha(
                        nome=filename, storage_path=storage_path,
                        tamanho=len(dados_bytes), extensao=Path(filename).suffix.lower(),
                        abas=abas,
                    )
                    _notificar_usuarios("upload", {"acao": "novo", "nome": filename, "id": meta.get("id")})
                    resultados.append({"id": meta.get("id", ""), "nome": filename, "status": "ok"})
            except Exception as e:
                logger.error(f"Upload error: {e}", exc_info=True)
                resultados.append({"nome": filename, "status": "erro", "mensagem": f"Erro no upload: {str(e)}"})
        else:
            try:
                final_path = UPLOAD_FOLDER / filename
                if final_path.exists():
                    stem, suffix = final_path.stem, final_path.suffix
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{stem}_{ts}{suffix}"
                    final_path = UPLOAD_FOLDER / filename
                    
                    # Criar backup do arquivo antigo
                    _criar_backup_local(str(final_path.parent / (stem + suffix)))
                
                with open(final_path, "wb") as f:
                    f.write(dados_bytes)

                info = _info_planilha(str(final_path))
                if info:
                    pid = _id_arquivo(str(final_path))
                    info.update({
                        "id": pid, "tags": [], "categoria": "", "descricao": "",
                        "favorito": False, "data_upload": datetime.now().isoformat(),
                    })
                    metadados = _carregar_metadados()
                    metadados[pid] = info
                    _salvar_metadados(metadados)
                    _notificar_usuarios("upload", {"acao": "novo", "nome": filename, "id": pid})
                    resultados.append({"id": pid, "nome": filename, "status": "ok"})
                else:
                    resultados.append({"nome": filename, "status": "erro", "mensagem": "Não foi possível ler o arquivo"})
            except Exception as e:
                logger.error(f"Upload local error: {e}", exc_info=True)
                resultados.append({"nome": filename, "status": "erro", "mensagem": f"Erro: {str(e)}"})

    return jsonify({"resultados": resultados, "total": len(resultados)})


# =============================================================================
# API - Delete / Update
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/delete", methods=["DELETE"])
def api_deletar(planilha_id: str):
    # Criar backup antes de deletar
    _criar_backup_versionamento(planilha_id, "delecao")
    
    if _supabase_disponivel():
        ok = _delete_planilha(planilha_id)
        if not ok:
            return jsonify({"erro": "Planilha não encontrada"}), 404
    else:
        _delete_planilha(planilha_id)
    
    meta = _get_planilha(planilha_id)
    _notificar_usuarios("delete", {"nome": meta.get("nome", "") if meta else "Desconhecida"})
    return jsonify({"status": "ok"})

@app.route("/api/planilhas/<planilha_id>/update", methods=["PUT"])
def api_atualizar(planilha_id: str):
    data: dict[str, Any] = request.json or {}
    
    # Criar versão antes de atualizar
    if any(k in data for k in ["nome", "descricao", "categoria", "tags"]):
        _criar_backup_versionamento(planilha_id, "atualizacao_metadata")
    
    _update_planilha(planilha_id, data)
    
    meta = _get_planilha(planilha_id)
    _notificar_usuarios("update", {"nome": meta.get("nome", "") if meta else "Desconhecida"})
    return jsonify({"status": "ok"})


# =============================================================================
# API - Notificações
# =============================================================================

@app.route("/api/notificacoes")
def api_notificacoes():
    """Retorna notificações não lidas."""
    nao_lidas = [n for n in notificacoes_cache if not n.get("lida")]
    return jsonify({
        "total": len(nao_lidas),
        "notificacoes": nao_lidas[:20]  # Últimas 20
    })


@app.route("/api/notificacoes/marcar-lida", methods=["POST"])
def api_marcar_lida():
    """Marca notificação como lida."""
    data = request.json or {}
    notif_id = data.get("id")
    
    if notif_id:
        for notif in notificacoes_cache:
            if notif["id"] == notif_id:
                notif["lida"] = True
                break
        
        with open(NOTIFICACOES_FILE, 'w', encoding='utf-8') as f:
            json.dump(notificacoes_cache, f, ensure_ascii=False, indent=2)
    
    return jsonify({"status": "ok"})


@app.route("/api/notificacoes/limpar", methods=["POST"])
def api_limpar_notificacoes():
    """Limpa todas as notificações."""
    global notificacoes_cache
    notificacoes_cache = []
    with open(NOTIFICACOES_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)
    return jsonify({"status": "ok"})


# =============================================================================
# API - Versionamento
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/versoes")
def api_listar_versoes(planilha_id: str):
    """Lista versões disponíveis de uma planilha."""
    versao_dir = VERSIONS_DIR / planilha_id
    if not versao_dir.exists():
        return jsonify([])
    
    versoes = []
    for versao_file in sorted(versao_dir.glob("v_*.json"), reverse=True):
        try:
            with open(versao_file, 'r', encoding='utf-8') as f:
                versao_info = json.load(f)
                versoes.append(versao_info)
        except Exception:
            continue
    
    return jsonify(versoes[:20])  # Últimas 20 versões


@app.route("/api/planilhas/<planilha_id>/restaurar/<version_id>", methods=["POST"])
def api_restaurar_versao(planilha_id: str, version_id: str):
    """Restaura uma versão anterior da planilha."""
    versao_dir = VERSIONS_DIR / planilha_id
    versao_file = versao_dir / f"{version_id}.json"
    
    if not versao_file.exists():
        return jsonify({"erro": "Versão não encontrada"}), 404
    
    try:
        with open(versao_file, 'r', encoding='utf-8') as f:
            versao_info = json.load(f)
        
        # Criar backup do estado atual antes de restaurar
        _criar_backup_versionamento(planilha_id, "rollback")
        
        # Restaura metadados
        metadata_snapshot = versao_info.get("metadata_snapshot", {})
        if metadata_snapshot:
            _update_planilha(planilha_id, {
                "nome": metadata_snapshot.get("nome"),
                "descricao": metadata_snapshot.get("descricao"),
                "categoria": metadata_snapshot.get("categoria"),
                "tags": metadata_snapshot.get("tags"),
            })
        
        # Se modo local, restaura arquivo físico
        if not _supabase_disponivel():
            versao_arquivo = versao_dir / f"{version_id}{Path(metadata_snapshot.get('nome', '')).suffix}"
            if versao_arquivo.exists():
                meta_atual = _get_planilha(planilha_id)
                if meta_atual:
                    caminho_atual = Path(meta_atual.get("caminho", ""))
                    import shutil
                    shutil.copy2(str(versao_arquivo), str(caminho_atual))
        
        _notificar_usuarios("update", {"nome": versao_info.get("nome", ""), "acao": "restaurado"})
        return jsonify({"status": "ok", "mensagem": "Versão restaurada com sucesso"})
        
    except Exception as e:
        logger.error(f"Erro ao restaurar versão: {e}", exc_info=True)
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# API - Exportação Avançada
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/exportar")
def api_exportar(planilha_id: str):
    """Exporta planilha em diferentes formatos."""
    meta = _get_planilha(planilha_id)
    if not meta:
        abort(404)
    
    formato = request.args.get("formato", "xlsx").lower()
    sheet_name = request.args.get("sheet", "")
    
    try:
        # Carrega dados da planilha
        if _supabase_disponivel():
            storage_path = meta.get("storage_path", "")
            if not storage_path:
                abort(404)
            dados_bytes = storage_backend.download_arquivo(storage_path)
            stream = io.BytesIO(dados_bytes)
        else:
            caminho = Path(meta.get("caminho", ""))
            if not caminho.exists():
                abort(404)
            stream = str(caminho)
        
        ext_original = Path(meta["nome"]).suffix.lower()
        
        if formato == "csv":
            # Exporta como CSV
            if ext_original == ".csv":
                return send_file(stream, as_attachment=True, download_name=f"{Path(meta['nome']).stem}.csv")
            else:
                df = pd.read_excel(stream, sheet_name=sheet_name if sheet_name else 0)
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_buffer.seek(0)
                return send_file(
                    io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                    as_attachment=True,
                    download_name=f"{Path(meta['nome']).stem}.csv",
                    mimetype='text/csv'
                )
        
        elif formato == "pdf":
            # Exporta como PDF (requere reportlab ou weasyprint)
            try:
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import letter, landscape
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
                
                pdf_buffer = io.BytesIO()
                doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(letter))
                
                # Lê primeira aba
                xl = pd.ExcelFile(stream)
                sheet = sheet_name if sheet_name else xl.sheet_names[0]
                df = xl.parse(sheet, nrows=100)  # Limita a 100 linhas para PDF
                
                # Converte DataFrame para tabela
                data = [df.columns.tolist()] + df.values.tolist()
                table = Table(data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ]))
                
                styles = getSampleStyleSheet()
                titulo = Paragraph(f"Planilha: {meta['nome']}", styles['Heading1'])
                
                doc.build([titulo, table])
                pdf_buffer.seek(0)
                
                return send_file(
                    pdf_buffer,
                    as_attachment=True,
                    download_name=f"{Path(meta['nome']).stem}.pdf",
                    mimetype='application/pdf'
                )
            except ImportError:
                return jsonify({"erro": "reportlab não instalado. Execute: pip install reportlab"}), 500
        
        else:
            # Formato padrão: xlsx
            return send_file(stream, as_attachment=True, download_name=meta["nome"])
            
    except Exception as e:
        logger.error(f"Erro na exportação: {e}", exc_info=True)
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# API - Download
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/download")
def api_download(planilha_id: str):
    meta = _get_planilha(planilha_id)
    if not meta:
        abort(404)

    if _supabase_disponivel():
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
def api_preview(planilha_id: str):
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404

    sheet = request.args.get("sheet", "")
    limite = min(int(request.args.get("limite", 50)), 200)
    ext = Path(meta["nome"]).suffix.lower()

    try:
        if _supabase_disponivel():
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
            dados: dict[str, Any] = {"abas": [{"nome": "Sheet1", "colunas": list(df.columns), "linhas": _df_para_lista(df), "total_linhas": len(df)}]}
        else:
            xl = pd.ExcelFile(stream)
            abas: List[Dict[str, Any]] = []
            for s in xl.sheet_names:
                if sheet and s != sheet:
                    continue
                df = xl.parse(s, nrows=limite)
                abas.append({"nome": s, "colunas": list(df.columns), "linhas": _df_para_lista(df), "total_linhas": len(df)})
            dados: dict[str, Any] = {"abas": abas}

        return jsonify(dados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# API - Tags / Categorias
# =============================================================================

@app.route("/api/tags")
def api_listar_tags():
    if _supabase_disponivel():
        return jsonify(storage_backend.listar_tags_categorias())
    metadados = _carregar_metadados()
    todas_tags: set[str] = set()
    categorias: set[str] = set()
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

def _parse_size(size_str: str) -> float:
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
    ext_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    categoria_counts: dict[str, int] = {}
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
                "extensoes": dict(sorted(ext_counts.items())),  # type: ignore[arg-type]
        "tags_mais_usadas": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10]),  # type: ignore[arg-type]
        "categorias": dict(sorted(categoria_counts.items())),  # type: ignore[arg-type]
        "total_tags": len(tag_counts),
        "favoritos": favoritos,
        "recentes_7dias": recentes,
    })
# =============================================================================
# API - Busca Full-Text
# =============================================================================

# Índice de busca full-text
INDICE_BUSCA_DIR = BASE_DIR / "indice_busca"
os.makedirs(INDICE_BUSCA_DIR, exist_ok=True)

try:
    from whoosh.index import create_in, open_dir  # type: ignore
    from whoosh.fields import Schema, TEXT, ID, NUMERIC  # type: ignore
    from whoosh.qparser import QueryParser  # type: ignore
    
    # Schema do índice
    schema = Schema(
        planilha_id=ID(stored=True),
        nome=TEXT(stored=True),
        conteudo=TEXT(stored=False),
        tags=TEXT(stored=True),
        categoria=TEXT(stored=True),
    )
    
    # Abre ou cria índice
    if (INDICE_BUSCA_DIR / "MAIN").exists():
        ix = open_dir(str(INDICE_BUSCA_DIR))
    else:
        ix = create_in(str(INDICE_BUSCA_DIR), schema)
    
    WHOOSH_AVAILABLE = True
except ImportError:
    WHOOSH_AVAILABLE = False
    logger.warning("Whoosh não instalado. Busca full-text desabilitada.")


def _indexar_planilha(planilha_id: str, meta: Dict[str, Any]) -> None:
    """Indexa conteúdo da planilha para busca full-text."""
    if not WHOOSH_AVAILABLE:
        return
    
    try:
        writer = ix.writer()
        
        # Extrai texto do conteúdo
        conteudo_texto = ""
        try:
            if _supabase_disponivel():
                storage_path = meta.get("storage_path", "")
                if storage_path:
                    dados_bytes = storage_backend.download_arquivo(storage_path)
                    stream = io.BytesIO(dados_bytes)
                else:
                    stream = None
            else:
                caminho = Path(meta.get("caminho", ""))
                if caminho.exists():
                    stream = str(caminho)
                else:
                    stream = None
            
            if stream:
                ext = Path(meta["nome"]).suffix.lower()
                if ext == ".csv":
                    df = pd.read_csv(stream, nrows=500)
                    conteudo_texto = " ".join(df.astype(str).values.flatten())
                else:
                    xl = pd.ExcelFile(stream)
                    textos = []
                    for sheet in xl.sheet_names[:3]:  # Indexa até 3 abas
                        df = xl.parse(sheet, nrows=200)
                        textos.append(" ".join(df.astype(str).values.flatten()))
                    conteudo_texto = " ".join(textos)
        except Exception as e:
            logger.warning(f"Erro ao extrair texto para indexação: {e}")
        
        # Adiciona ao índice
        writer.update_document(
            planilha_id=planilha_id,
            nome=meta.get("nome", ""),
            conteudo=conteudo_texto[:10000],  # Limita tamanho
            tags=" ".join(meta.get("tags", [])),
            categoria=meta.get("categoria", ""),
        )
        writer.commit()
        
    except Exception as e:
        logger.error(f"Erro ao indexar planilha {planilha_id}: {e}")


@app.route("/api/buscar-fulltext")
def api_buscar_fulltext():
    """Busca full-text em nomes, tags e conteúdo das planilhas."""
    q = request.args.get("q", "").strip()
    if not q or not WHOOSH_AVAILABLE:
        # Fallback para busca simples
        return api_buscar()
    
    try:
        with ix.searcher() as searcher:
            # Busca em múltiplos campos
            parser = QueryParser("conteudo", ix.schema)
            query = parser.parse(q)
            
            resultados = []
            for hit in searcher.search(query, limit=30):
                planilha_id = hit["planilha_id"]
                meta = _get_planilha(planilha_id)
                if meta:
                    resultados.append({
                        "id": planilha_id,
                        "nome": meta.get("nome", ""),
                        "tamanho_formatado": meta.get("tamanho_formatado", ""),
                        "tags": meta.get("tags", []),
                        "categoria": meta.get("categoria", ""),
                        "score": hit.score,
                    })
            
            # Ordena por score
            resultados.sort(key=lambda x: -x["score"])
            return jsonify(resultados)
            
    except Exception as e:
        logger.error(f"Erro na busca full-text: {e}")
        return api_buscar()  # Fallback


# =============================================================================
# API - Compressão
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/comprimir", methods=["POST"])
def api_comprimir(planilha_id: str):
    """Comprime arquivo da planilha se for maior que 10MB."""
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404
    
    tamanho = meta.get("tamanho", 0)
    if tamanho < 10 * 1024 * 1024:  # Menor que 10MB
        return jsonify({"status": "ok", "mensagem": "Arquivo já está pequeno"})
    
    try:
        # Download do arquivo
        if _supabase_disponivel():
            storage_path = meta.get("storage_path", "")
            if not storage_path:
                return jsonify({"erro": "Arquivo não encontrado"}), 404
            dados_bytes = storage_backend.download_arquivo(storage_path)
        else:
            caminho = Path(meta.get("caminho", ""))
            if not caminho.exists():
                return jsonify({"erro": "Arquivo não encontrado"}), 404
            with open(caminho, 'rb') as f:
                dados_bytes = f.read()
        
        # Tenta otimizar Excel removendo formatação desnecessária
        ext = Path(meta["nome"]).suffix.lower()
        if ext in ['.xlsx', '.xlsm']:
            try:
                # Lê e reescreve para remover formatação excessiva
                df_dict = pd.read_excel(io.BytesIO(dados_bytes), sheet_name=None)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for sheet_name, df in df_dict.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                dados_otimizados = output.getvalue()
                
                # Só substitui se realmente menor
                if len(dados_otimizados) < len(dados_bytes) * 0.9:  # Pelo menos 10% menor
                    # Backup antes
                    _criar_backup_versionamento(planilha_id, "compressao")
                    
                    if _supabase_disponivel():
                        storage_backend.deletar_arquivo_storage(storage_path)
                        novo_path = storage_backend.upload_arquivo(meta["nome"], dados_otimizados)
                        storage_backend.atualizar_planilha(planilha_id, {
                            "storage_path": novo_path,
                            "tamanho": len(dados_otimizados),
                            "tamanho_formatado": _formatar_tamanho(len(dados_otimizados)),
                        })
                    else:
                        caminho = Path(meta.get("caminho", ""))
                        with open(caminho, 'wb') as f:
                            f.write(dados_otimizados)
                        meta["tamanho"] = len(dados_otimizados)
                        meta["tamanho_formatado"] = _formatar_tamanho(len(dados_otimizados))
                        _update_planilha(planilha_id, meta)
                    
                    reducao = ((len(dados_bytes) - len(dados_otimizados)) / len(dados_bytes)) * 100
                    return jsonify({
                        "status": "ok",
                        "mensagem": f"Arquivo comprimido: {reducao:.1f}% de redução",
                        "tamanho_anterior": _formatar_tamanho(len(dados_bytes)),
                        "tamanho_novo": _formatar_tamanho(len(dados_otimizados)),
                    })
            except Exception as e:
                logger.warning(f"Não foi possível otimizar Excel: {e}")
        
        return jsonify({"status": "ok", "mensagem": "Arquivo não pôde ser comprimido adicionalmente"})
        
    except Exception as e:
        logger.error(f"Erro na compressão: {e}", exc_info=True)
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# API - Busca
# =============================================================================

@app.route("/api/buscar")
def api_buscar():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    planilhas = _get_planilhas()
    resultados: List[Dict[str, Any]] = []
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
    if _supabase_disponivel():
        return jsonify({"adicionados": 0, "total": len(_get_planilhas())})
    metadados = _carregar_metadados()
    adicionados = 0
    for arquivo in UPLOAD_FOLDER.iterdir():
        if not arquivo.is_file() or arquivo.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        pid = _id_arquivo(str(arquivo))
        if pid not in metadados:
            info = _info_planilha(str(arquivo))
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
# API - Validação de Dados
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/validar")
def api_validar(planilha_id: str):
    """Valida dados da planilha buscando problemas comuns."""
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404
    
    try:
        # Carrega dados
        if _supabase_disponivel():
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
        
        ext = Path(meta["nome"]).suffix.lower()
        problemas = []
        estatisticas = {}
        
        if ext == ".csv":
            df = pd.read_csv(stream)
            estatisticas["total_linhas"] = len(df)
            estatisticas["total_colunas"] = len(df.columns)
        else:
            xl = pd.ExcelFile(stream)
            total_linhas = 0
            total_celulas_vazias = 0
            total_duplicatas = 0
            
            for sheet in xl.sheet_names:
                df = xl.parse(sheet)
                total_linhas += len(df)
                
                # Verifica células vazias
                celulas_vazias = df.isnull().sum().sum()
                total_celulas_vazias += celulas_vazias
                
                # Verifica duplicatas
                duplicatas = df.duplicated().sum()
                total_duplicatas += duplicatas
                
                # Verifica tipos inconsistentes
                for col in df.columns:
                    valores_nao_numericos = pd.to_numeric(df[col], errors='coerce').isnull().sum()
                    if valores_nao_numericos > 0 and valores_nao_numericos < len(df):
                        problemas.append({
                            "tipo": "tipo_misto",
                            "aba": sheet,
                            "coluna": col,
                            "mensagem": f"Coluna '{col}' tem valores mistos (texto e números)",
                            "severidade": "warning"
                        })
            
            estatisticas["total_linhas"] = total_linhas
            estatisticas["total_abas"] = len(xl.sheet_names)
            
            if total_celulas_vazias > 0:
                problemas.append({
                    "tipo": "celulas_vazias",
                    "total": int(total_celulas_vazias),
                    "mensagem": f"{total_celulas_vazias} células vazias encontradas",
                    "severidade": "info"
                })
            
            if total_duplicatas > 0:
                problemas.append({
                    "tipo": "duplicatas",
                    "total": int(total_duplicatas),
                    "mensagem": f"{total_duplicatas} linhas duplicadas encontradas",
                    "severidade": "warning"
                })
        
        # Verifica tamanho do arquivo
        tamanho_mb = meta.get("tamanho", 0) / (1024 * 1024)
        if tamanho_mb > 50:
            problemas.append({
                "tipo": "arquivo_grande",
                "tamanho_mb": round(tamanho_mb, 2),
                "mensagem": f"Arquivo muito grande ({tamanho_mb:.2f} MB). Considere comprimir.",
                "severidade": "warning"
            })
        
        return jsonify({
            "status": "ok",
            "problemas": problemas,
            "estatisticas": estatisticas,
            "total_problemas": len(problemas),
        })
        
    except Exception as e:
        logger.error(f"Erro na validação: {e}", exc_info=True)
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# EDIÇÃO COLABORATIVA - Cache e suporte a Socket.IO
# =============================================================================

def _carregar_planilha_cache(planilha_id: str) -> bool:
    """Carrega dados completos de uma planilha para o cache de edição."""
    meta = _get_planilha(planilha_id)
    if not meta:
        return False

    try:
        ext = Path(meta["nome"]).suffix.lower()
        if _supabase_disponivel():
            storage_path = meta.get("storage_path", "")
            if not storage_path:
                return False
            dados_bytes = storage_backend.download_arquivo(storage_path)
            stream = io.BytesIO(dados_bytes)
        else:
            caminho = Path(meta.get("caminho", ""))
            if not caminho.exists():
                return False
            stream = str(caminho)

        sheets = {}
        if ext == ".csv":
            df = pd.read_csv(stream)
            sheets["Sheet1"] = {
                "colunas": list(df.columns),
                "linhas": _df_para_lista(df),
            }
        else:
            xl = pd.ExcelFile(stream)
            for s in xl.sheet_names:
                df = xl.parse(s)
                sheets[s] = {
                    "colunas": list(df.columns),
                    "linhas": _df_para_lista(df),
                }

        with cache_lock:
            planilha_cache[planilha_id] = {
                "meta": meta,
                "sheets": sheets,
            }
        return True
    except Exception as e:
        logger.error(f"Erro ao carregar planilha no cache: {e}")
        return False


def _salvar_planilha_cache(planilha_id: str) -> bool:
    """Salva o cache de edição de volta para o storage."""
    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if not cache:
            return False

        meta = cache["meta"]
        sheets = cache["sheets"]

    try:
        buffer = io.BytesIO()
        ext = Path(meta["nome"]).suffix.lower()

        if ext == ".csv":
            if sheets:
                sheet_name = list(sheets.keys())[0]
                s = sheets[sheet_name]
                df = pd.DataFrame(s["linhas"], columns=s["colunas"])
                df.to_csv(buffer, index=False)
        else:
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                for sheet_name, s in sheets.items():
                    df = pd.DataFrame(s["linhas"], columns=s["colunas"])
                    df.to_excel(writer, sheet_name=sheet_name, index=False)  # type: ignore[arg-type]
        buffer.seek(0)
        dados_bytes = buffer.getvalue()

        if _supabase_disponivel():
            storage_path = meta.get("storage_path", "")
            if storage_path:
                storage_backend.deletar_arquivo_storage(storage_path)
            novo_path = storage_backend.upload_arquivo(meta["nome"], dados_bytes)
            storage_backend.atualizar_planilha(planilha_id, {
                "storage_path": novo_path,
                "tamanho": len(dados_bytes),
                "tamanho_formatado": _formatar_tamanho(len(dados_bytes)),
                "ultima_modificacao": datetime.now().isoformat(),
            })
            with cache_lock:
                if planilha_id in planilha_cache:
                    planilha_cache[planilha_id]["meta"] = _get_planilha(planilha_id)
        else:
            caminho = Path(meta.get("caminho", ""))
            with open(caminho, "wb") as f:
                f.write(dados_bytes)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar planilha do cache: {e}")
        return False


# =============================================================================
# API - Edição: dados completos
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/edit-data")
def api_edit_data(planilha_id: str):
    """Retorna TODOS os dados da planilha para edição."""
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404

    # Carrega no cache se não estiver
    with cache_lock:
        if planilha_id not in planilha_cache:
            ok = _carregar_planilha_cache(planilha_id)
            if not ok:
                return jsonify({"erro": "Não foi possível carregar a planilha"}), 500

    with cache_lock:
        cache = planilha_cache.get(planilha_id)

    if not cache:
        return jsonify({"erro": "Cache não disponível"}), 500

    return jsonify({
        "meta": {
            "nome": meta["nome"],
            "extensao": Path(meta["nome"]).suffix.lower(),
        },
        "sheets": {
            name: {
                "colunas": s["colunas"],
                "linhas": s["linhas"],
            }
            for name, s in cache["sheets"].items()
        },
        "sheet_names": list(cache["sheets"].keys()),
    })


# =============================================================================
# API - Salvar edição
# =============================================================================

@app.route("/api/planilhas/<planilha_id>/save", methods=["POST"])
def api_save_planilha(planilha_id: str):
    """Salva as alterações da planilha (do cache) para o storage."""
    meta = _get_planilha(planilha_id)
    if not meta:
        return jsonify({"erro": "Planilha não encontrada"}), 404

    try:
        data: dict[str, Any] = request.json or {}
        sheets_data = data.get("sheets")

        if sheets_data:
            with cache_lock:
                if planilha_id not in planilha_cache:
                    ok = _carregar_planilha_cache(planilha_id)
                    if not ok:
                        return jsonify({"erro": "Não foi possível carregar"}), 500

            with cache_lock:
                cache = planilha_cache.get(planilha_id)
                if cache:
                    for sheet_name, sheet_data in sheets_data.items():
                        if sheet_name in cache["sheets"]:
                            if sheet_data.get("linhas") is not None:
                                cache["sheets"][sheet_name]["linhas"] = sheet_data["linhas"]
                            if sheet_data.get("colunas") is not None:
                                cache["sheets"][sheet_name]["colunas"] = sheet_data["colunas"]

        ok = _salvar_planilha_cache(planilha_id)
        if ok:
            # Notifica todos na sala sobre o salvamento
            _emit_data: dict[str, Any] = {"planilha_id": planilha_id, "timestamp": datetime.now().isoformat()}
            socketio.emit("planilha_salva", _emit_data, room=planilha_id)  # type: ignore[call-arg]

            return jsonify({"status": "ok", "mensagem": "Planilha salva com sucesso!"})
        else:
            return jsonify({"erro": "Erro ao salvar planilha"}), 500
    except Exception as e:
        logger.error(f"Save error: {e}")
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# SOCKET.IO - Helpers
# =============================================================================

def _contar_usuarios_sala(planilha_id: str) -> int:
    """Conta quantos sockets estão em uma sala."""
    try:
        _server: Any = socketio  # type: ignore[attr-defined]
        _manager: Any = getattr(_server, 'server', None)
        _rooms: Any = getattr(_manager, 'rooms', {}) if _manager else {}
        return len(_rooms.get("/", {}).get(planilha_id, set())) if _rooms else 0
    except Exception:
        return 0


# =============================================================================
# SOCKET.IO - Eventos de colaboração em tempo real
# =============================================================================

@socketio.on("connect")
def handle_connect():
    logger.info(f"Cliente conectado: {request.sid}")  # type: ignore[attr-defined]


@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Cliente desconectado: {request.sid}")  # type: ignore[attr-defined]


@socketio.on("join_planilha")
def handle_join(data: dict[str, Any]):
    planilha_id = data.get("planilha_id")
    if not planilha_id:
        return

    join_room(planilha_id)

    # Garante que a planilha está no cache
    with cache_lock:
        if planilha_id not in planilha_cache:
            _carregar_planilha_cache(planilha_id)

    # Informa os outros na sala
    emit("usuario_entrou", {"sid": request.sid}, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]

    # Conta quantos usuarios estão na sala (inclui o que entrou)
    room_users = _contar_usuarios_sala(planilha_id)
    socketio.emit("usuarios_na_sala", {"count": room_users}, room=planilha_id)  # type: ignore[call-arg]


@socketio.on("leave_planilha")
def handle_leave(data: dict[str, Any]):
    planilha_id = data.get("planilha_id")
    if planilha_id:
        leave_room(planilha_id)
        emit("usuario_saiu", {"sid": request.sid}, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]

        room_users = _contar_usuarios_sala(planilha_id)
        socketio.emit("usuarios_na_sala", {"count": room_users}, room=planilha_id)  # type: ignore[call-arg]


@socketio.on("celula_editada")
def handle_cell_edit(data: dict[str, Any]):
    """Recebe edição de uma célula e propaga para os outros na sala."""
    planilha_id: Any = data.get("planilha_id")
    sheet: Any = data.get("sheet")
    row: Any = data.get("row")
    col: Any = data.get("col")
    valor: Any = data.get("valor")

    if not planilha_id or not sheet or row is None or col is None:
        return

    # Atualiza o cache em memória
    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if cache and sheet in cache["sheets"]:
            linhas = cache["sheets"][sheet]["linhas"]
            if 0 <= row < len(linhas) and 0 <= col < len(cache["sheets"][sheet]["colunas"]):
                linhas[row][col] = valor

    # Broadcast para todos na sala (exclui o remetente, ele já atualizou localmente)
    emit("celula_atualizada", data, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]


@socketio.on("linha_adicionada")
def handle_row_add(data: dict[str, Any]):
    """Recebe inserção de nova linha."""
    planilha_id: Any = data.get("planilha_id")
    sheet: Any = data.get("sheet")
    index: Any = data.get("index")

    if not planilha_id or not sheet or index is None:
        return

    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if cache and sheet in cache["sheets"]:
            num_cols = len(cache["sheets"][sheet]["colunas"])
            nova_linha = [None] * num_cols
            cache["sheets"][sheet]["linhas"].insert(index, nova_linha)

    emit("linha_adicionada", data, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]


@socketio.on("linha_removida")
def handle_row_remove(data: dict[str, Any]):
    """Recebe remoção de linha."""
    planilha_id: Any = data.get("planilha_id")
    sheet: Any = data.get("sheet")
    index: Any = data.get("index")

    if not planilha_id or not sheet or index is None:
        return

    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if cache and sheet in cache["sheets"]:
            linhas = cache["sheets"][sheet]["linhas"]
            if 0 <= index < len(linhas):
                cache["sheets"][sheet]["linhas"].pop(index)

    emit("linha_removida", data, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]


@socketio.on("coluna_adicionada")
def handle_col_add(data: dict[str, Any]):
    planilha_id: Any = data.get("planilha_id")
    sheet: Any = data.get("sheet")
    nome: Any = data.get("nome", "Nova Coluna")
    index: Any = data.get("index")

    if not planilha_id or not sheet:
        return

    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if cache and sheet in cache["sheets"]:
            cols = cache["sheets"][sheet]["colunas"]
            idx = min(index, len(cols)) if index is not None else len(cols)
            cols.insert(idx, nome)
            for linha in cache["sheets"][sheet]["linhas"]:
                linha.insert(idx, None)

    emit("coluna_adicionada", data, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]


@socketio.on("coluna_removida")
def handle_col_remove(data: dict[str, Any]):
    planilha_id: Any = data.get("planilha_id")
    sheet: Any = data.get("sheet")
    index: Any = data.get("index")

    if not planilha_id or not sheet or index is None:
        return

    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if cache and sheet in cache["sheets"]:
            cols = cache["sheets"][sheet]["colunas"]
            if 0 <= index < len(cols):
                cols.pop(index)
                for linha in cache["sheets"][sheet]["linhas"]:
                    if 0 <= index < len(linha):
                        linha.pop(index)

    emit("coluna_removida", data, room=planilha_id, skip_sid=request.sid)  # type: ignore[call-arg,attr-defined]


# =============================================================================
# SOCKET.IO - COLABORAÇÃO EM TEMPO REAL COMPLETA
# =============================================================================

# Locks de edição por planilha
edit_locks: Dict[str, Dict[str, Any]] = {}
# {planilha_id: {"user": user_id, "sheet": sheet_name, "timestamp": datetime}}


@socketio.on('connect')
def handle_connect():
    """Cliente conectou."""
    logger.info(f"Cliente conectado: {request.sid}")  # type: ignore[attr-defined]
    emit('status', {'msg': 'Conectado ao servidor'})


@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectou - libera locks."""
    sid = request.sid  # type: ignore[attr-defined]
    
    # Libera todos os locks deste usuário
    for planilha_id, lock_info in list(edit_locks.items()):
        if lock_info.get("sid") == sid:
            del edit_locks[planilha_id]
            emit('lock_released', {
                'planilha_id': planilha_id,
                'user': lock_info.get('user', 'Desconhecido')
            }, room=planilha_id)
    
    logger.info(f"Cliente desconectado: {sid}")


@socketio.on('join_planilha')
def handle_join_planilha(data):
    """Usuário entra em uma sala de edição de planilha."""
    planilha_id = data.get('planilha_id')
    user = data.get('user', 'Anônimo')
    
    if planilha_id:
        join_room(planilha_id)  # type: ignore[call-arg]
        
        # Verifica se há lock ativo
        lock_info = edit_locks.get(planilha_id)
        if lock_info:
            emit('lock_status', {
                'locked': True,
                'user': lock_info.get('user'),
                'since': lock_info.get('timestamp')
            })
        else:
            emit('lock_status', {'locked': False})
        
        # Notifica outros usuários
        emit('user_joined', {
            'user': user,
            'total_users': len(socketio.server.manager.rooms.get(planilha_id, set()))  # type: ignore[attr-defined]
        }, room=planilha_id, include_self=False)
        
        logger.info(f"Usuário {user} entrou na planilha {planilha_id}")


@socketio.on('leave_planilha')
def handle_leave_planilha(data):
    """Usuário sai da sala de edição."""
    planilha_id = data.get('planilha_id')
    user = data.get('user', 'Anônimo')
    
    if planilha_id:
        leave_room(planilha_id)  # type: ignore[call-arg]
        
        # Libera lock se pertence a este usuário
        lock_info = edit_locks.get(planilha_id)
        if lock_info and lock_info.get('sid') == request.sid:  # type: ignore[attr-defined]
            del edit_locks[planilha_id]
            emit('lock_released', {'user': user}, room=planilha_id)
        
        emit('user_left', {
            'user': user,
            'total_users': max(0, len(socketio.server.manager.rooms.get(planilha_id, set())) - 1)  # type: ignore[attr-defined]
        }, room=planilha_id, include_self=False)


@socketio.on('request_lock')
def handle_request_lock(data):
    """Usuário solicita lock para editar."""
    planilha_id = data.get('planilha_id')
    sheet = data.get('sheet')
    user = data.get('user', 'Anônimo')
    
    if not planilha_id:
        return
    
    # Verifica se já existe lock
    if planilha_id in edit_locks:
        lock_info = edit_locks[planilha_id]
        emit('lock_denied', {
            'message': f'Planilha bloqueada por {lock_info.get("user")}',
            'user': lock_info.get('user'),
            'since': lock_info.get('timestamp')
        })
    else:
        # Concede lock
        edit_locks[planilha_id] = {
            'sid': request.sid,  # type: ignore[attr-defined]
            'user': user,
            'sheet': sheet,
            'timestamp': datetime.now().isoformat()
        }
        
        emit('lock_granted', {
            'planilha_id': planilha_id,
            'sheet': sheet,
            'user': user
        })
        
        # Notifica outros
        emit('planilha_locked', {
            'user': user,
            'sheet': sheet
        }, room=planilha_id, include_self=False)


@socketio.on('release_lock')
def handle_release_lock(data):
    """Usuário libera o lock."""
    planilha_id = data.get('planilha_id')
    user = data.get('user', 'Anônimo')
    
    if planilha_id and planilha_id in edit_locks:
        lock_info = edit_locks[planilha_id]
        if lock_info.get('sid') == request.sid:  # type: ignore[attr-defined]
            del edit_locks[planilha_id]
            
            emit('lock_released', {'user': user}, room=planilha_id)
            logger.info(f"Lock liberado por {user} na planilha {planilha_id}")


@socketio.on('cell_edit')
def handle_cell_edit(data):
    """Edição de célula em tempo real."""
    planilha_id = data.get('planilha_id')
    sheet = data.get('sheet')
    row = data.get('row')
    col = data.get('col')
    value = data.get('value')
    user = data.get('user', 'Anônimo')
    
    if not planilha_id or sheet is None or row is None or col is None:
        return
    
    # Verifica lock
    if planilha_id in edit_locks:
        lock_info = edit_locks[planilha_id]
        if lock_info.get('sid') != request.sid:  # type: ignore[attr-defined]
            emit('edit_denied', {'message': 'Você não tem permissão para editar'})
            return
    
    # Atualiza cache
    with cache_lock:
        cache = planilha_cache.get(planilha_id)
        if cache and sheet in cache['sheets']:
            linhas = cache['sheets'][sheet]['linhas']
            if 0 <= row < len(linhas) and 0 <= col < len(linhas[row]):
                old_value = linhas[row][col]
                linhas[row][col] = value
                
                # Emite para outros usuários
                emit('cell_updated', {
                    'sheet': sheet,
                    'row': row,
                    'col': col,
                    'value': value,
                    'old_value': old_value,
                    'user': user,
                    'timestamp': datetime.now().isoformat()
                }, room=planilha_id, include_self=False)
                
                logger.debug(f"Célula editada: {sheet}[{row},{col}] = {value} por {user}")


@socketio.on('cursor_move')
def handle_cursor_move(data):
    """Movimento do cursor do usuário (para mostrar posição)."""
    planilha_id = data.get('planilha_id')
    user = data.get('user', 'Anônimo')
    row = data.get('row')
    col = data.get('col')
    
    if planilha_id:
        emit('cursor_moved', {
            'user': user,
            'row': row,
            'col': col,
            'timestamp': datetime.now().isoformat()
        }, room=planilha_id, include_self=False)


@socketio.on('chat_message')
def handle_chat_message(data):
    """Mensagem de chat na sala de colaboração."""
    planilha_id = data.get('planilha_id')
    user = data.get('user', 'Anônimo')
    message = data.get('message', '')
    
    if planilha_id and message:
        emit('new_chat_message', {
            'user': user,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }, room=planilha_id)


# =============================================================================
# INICIALIZAÇÃO
# =============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("=" * 60)
    print("  📊 Gerenciador de Planilhas")
    print(f"  Modo: {'Netlify + Supabase' if IS_NETLIFY else 'Local (arquivos)'}")
    print(f"  Porta: {port}")
    print("=" * 60)
    socketio.run(app, debug=True, host="0.0.0.0", port=port)  # type: ignore[arg-type]
