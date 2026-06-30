"""
Teste de conexão com Supabase
"""
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_KEY configurado: {'Sim' if SUPABASE_KEY else 'Não'}")
print(f"Key length: {len(SUPABASE_KEY) if SUPABASE_KEY else 0}")

try:
    from supabase import create_client
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Testar listagem da tabela
    resp = supabase.table("planilhas").select("id").limit(1).execute()
    print(f"\n✅ Conexão bem-sucedida!")
    print(f"Registros encontrados: {len(resp.data)}")
    
except Exception as e:
    print(f"\n❌ Erro: {type(e).__name__}: {e}")
