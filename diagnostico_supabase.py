#!/usr/bin/env python3
"""
Diagnóstico do Supabase no Render
"""
import os
import sys

print("=" * 60)
print("DIAGNÓSTICO DO SUPABASE")
print("=" * 60)

# Verificar variáveis de ambiente
print("\n1. Variáveis de Ambiente:")
print(f"   SUPABASE_URL: {os.getenv('SUPABASE_URL', 'NÃO DEFINIDA')}")
print(f"   SUPABASE_SERVICE_KEY: {'DEFINIDA' if os.getenv('SUPABASE_SERVICE_KEY') else 'NÃO DEFINIDA'}")
print(f"   SUPABASE_BUCKET: {os.getenv('SUPABASE_BUCKET', 'NÃO DEFINIDA')}")
print(f"   NETLIFY: {os.getenv('NETLIFY', 'NÃO DEFINIDA')}")

# Testar conexão
print("\n2. Testando Conexão:")
try:
    from supabase import create_client
    
    url = os.getenv('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_SERVICE_KEY', '')
    
    if not url or not key:
        print("   ❌ ERRO: Credenciais não configuradas!")
        sys.exit(1)
    
    supabase = create_client(url, key)
    print("   ✅ Cliente criado com sucesso")
    
    # Testar listagem da tabela
    print("\n3. Testando Tabela 'planilhas':")
    resp = supabase.table("planilhas").select("id").limit(1).execute()
    print(f"   ✅ Tabela acessível! Registros: {len(resp.data)}")
    
    # Testar bucket
    print("\n4. Testando Bucket:")
    bucket_name = os.getenv('SUPABASE_BUCKET', 'planilhas')
    buckets = supabase.storage.list_buckets()
    bucket_names = [b.name for b in buckets]
    print(f"   Buckets disponíveis: {bucket_names}")
    
    if bucket_name in bucket_names:
        print(f"   ✅ Bucket '{bucket_name}' encontrado!")
    else:
        print(f"   ❌ Bucket '{bucket_name}' NÃO encontrado!")
        
except Exception as e:
    print(f"   ❌ ERRO: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
