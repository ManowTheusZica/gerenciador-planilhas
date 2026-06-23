"""
Cliente Supabase - Conexão e operações com banco e storage.
Usa variáveis de ambiente:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY (service_role key, não anon)
    SUPABASE_BUCKET (opcional, default = 'planilhas')
"""
import os
import io
import json
import logging
from datetime import datetime
from pathlib import Path

from supabase import create_client, Client
import pandas as pd

logger = logging.getLogger("supabase")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
BUCKET_NAME = os.getenv("SUPABASE_BUCKET", "planilhas")

_supabase: Client | None = None


def get_client() -> Client:
    """Retorna o cliente Supabase (singleton)."""
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "Supabase não configurado. Defina SUPABASE_URL e SUPABASE_SERVICE_KEY "
                "no arquivo .env ou nas variáveis de ambiente."
            )
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        _inicializar_bucket()
    return _supabase


def _inicializar_bucket():
    """Garante que o bucket de storage existe."""
    try:
        supabase = _supabase
        buckets = supabase.storage.list_buckets()
        nomes = [b.name for b in buckets]
        if BUCKET_NAME not in nomes:
            supabase.storage.create_bucket(
                BUCKET_NAME,
                options={"public": False}
            )
            logger.info(f"Bucket '{BUCKET_NAME}' criado")
    except Exception as e:
        logger.warning(f"Bucket init: {e}")


# ---------------------------------------------------------------------------
# Metadados (PostgreSQL)
# ---------------------------------------------------------------------------

def listar_planilhas() -> list[dict]:
    """Lista todas as planilhas com metadados."""
    supabase = get_client()
    resp = supabase.table("planilhas").select("*").order("favorito", desc=True).order("nome").execute()
    dados = []
    for row in resp.data:
        row["tags"] = row.get("tags") or []
        row["abas"] = row.get("abas") or []
        row["favorito"] = bool(row.get("favorito", False))
        dados.append(_row_para_dict(row))
    return dados


def obter_planilha(planilha_id: str) -> dict | None:
    """Obtém uma planilha pelo ID."""
    supabase = get_client()
    resp = supabase.table("planilhas").select("*").eq("id", planilha_id).execute()
    if not resp.data:
        return None
    row = resp.data[0]
    return _row_para_dict(row)


def criar_planilha(nome: str, storage_path: str, tamanho: int,
                   extensao: str, abas: list) -> dict:
    """Cria um novo registro de planilha."""
    supabase = get_client()
    now = datetime.now().isoformat()
    data = {
        "nome": nome,
        "storage_path": storage_path,
        "tamanho": tamanho,
        "tamanho_formatado": _formatar_tamanho(tamanho),
        "extensao": extensao,
        "ultima_modificacao": now,
        "data_upload": now,
        "descricao": "",
        "favorito": False,
        "categoria": "",
        "tags": [],
        "abas": json.dumps(abas, ensure_ascii=False),
    }
    resp = supabase.table("planilhas").insert(data).execute()
    return _row_para_dict(resp.data[0]) if resp.data else data


def atualizar_planilha(planilha_id: str, dados: dict) -> dict | None:
    """Atualiza metadados de uma planilha."""
    supabase = get_client()
    update = {k: v for k, v in dados.items() if k in (
        "nome", "descricao", "favorito", "categoria", "tags", "abas"
    )}
    if "tags" in update and isinstance(update["tags"], list):
        update["tags"] = json.dumps(update["tags"])
    if "abas" in update and isinstance(update["abas"], (list, dict)):
        update["abas"] = json.dumps(update["abas"])
    update["updated_at"] = datetime.now().isoformat()
    resp = supabase.table("planilhas").update(update).eq("id", planilha_id).execute()
    return _row_para_dict(resp.data[0]) if resp.data else None


def deletar_planilha(planilha_id: str) -> bool:
    """Exclui uma planilha (metadados + arquivo do storage)."""
    supabase = get_client()
    meta = obter_planilha(planilha_id)
    if not meta:
        return False

    # Remove do storage
    storage_path = meta.get("storage_path", "")
    if storage_path:
        try:
            supabase.storage.from_(BUCKET_NAME).remove([storage_path])
        except Exception as e:
            logger.warning(f"Erro ao remover do storage: {e}")

    # Remove metadados
    supabase.table("planilhas").delete().eq("id", planilha_id).execute()
    return True


def _row_para_dict(row: dict) -> dict:
    """Converte row do Supabase para dict padronizado."""
    if isinstance(row.get("tags"), str):
        row["tags"] = json.loads(row["tags"])
    if isinstance(row.get("abas"), str):
        row["abas"] = json.loads(row["abas"])
    row["favorito"] = bool(row.get("favorito", False))
    return row


# ---------------------------------------------------------------------------
# Tags / Categorias
# ---------------------------------------------------------------------------

def listar_tags_categorias() -> dict:
    """Lista todas as tags e categorias em uso."""
    supabase = get_client()
    resp = supabase.table("planilhas").select("tags,categoria").execute()
    todas_tags = set()
    categorias = set()
    for row in resp.data:
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = json.loads(tags)
        for t in tags:
            todas_tags.add(t)
        if row.get("categoria"):
            categorias.add(row["categoria"])
    return {
        "tags": sorted(t for t in todas_tags if t),
        "categorias": sorted(c for c in categorias if c),
    }


# ---------------------------------------------------------------------------
# Storage (arquivos Excel)
# ---------------------------------------------------------------------------

def upload_arquivo(nome_arquivo: str, dados_bytes: bytes) -> str:
    """Faz upload de um arquivo para o Supabase Storage.
    Retorna o caminho (path) no storage."""
    supabase = get_client()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    storage_path = f"{timestamp}_{nome_arquivo}"

    supabase.storage.from_(BUCKET_NAME).upload(
        storage_path,
        dados_bytes,
        {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    return storage_path


def download_arquivo(storage_path: str) -> bytes:
    """Faz download de um arquivo do Supabase Storage."""
    supabase = get_client()
    resp = supabase.storage.from_(BUCKET_NAME).download(storage_path)
    return resp


def get_public_url(storage_path: str) -> str:
    """Gera URL pública (requer bucket público) ou URL signed."""
    supabase = get_client()
    return supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _formatar_tamanho(bytes_val: int) -> str:
    """Formata bytes para humano legível."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def extrair_info_planilha(arquivo_bytes: bytes, nome: str) -> tuple[list, int]:
    """Extrai informações das abas de uma planilha.
    Retorna (abas, tamanho)."""
    import pandas as pd
    import numpy as np

    ext = Path(nome).suffix.lower()
    abas = []
    tamanho = len(arquivo_bytes)

    try:
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(arquivo_bytes), nrows=100)
            abas.append({
                "nome": "Sheet1",
                "linhas": len(df) + 1,
                "colunas": len(df.columns),
                "colunas_nomes": list(df.columns),
            })
        else:
            xl = pd.ExcelFile(io.BytesIO(arquivo_bytes))
            for sheet in xl.sheet_names:
                df = xl.parse(sheet, nrows=100)
                abas.append({
                    "nome": sheet,
                    "linhas": len(df) + 1,
                    "colunas": len(df.columns),
                    "colunas_nomes": list(df.columns),
                })
    except Exception as e:
        abas.append({"nome": "Erro", "linhas": 0, "colunas": 0, "erro": str(e)})

    return abas, tamanho
