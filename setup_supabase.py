"""
Script para configurar o Supabase via API:
1. Cria projeto
2. Executa schema SQL
3. Cria bucket de storage
"""
import requests
import json
import sys
import time

TOKEN = "sbp_593d5e9ee8bb02f6856c72707d1d8e71523d4f83"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
API = "https://api.supabase.com"


def log(msg):
    print(f"  {msg}")


def main():
    # 1. Listar organizações
    log("📋 Listando organizações...")
    r = requests.get(f"{API}/v1/organizations", headers=HEADERS, timeout=10)
    if not r.ok:
        log(f"❌ Erro: {r.text[:300]}")
        sys.exit(1)
    
    orgs = r.json()
    if not orgs:
        log("❌ Nenhuma organização encontrada!")
        sys.exit(1)
    
    org_id = orgs[0]["id"]
    log(f"✅ Organização: {orgs[0]['name']} (ID: {org_id})")
    
    # 2. Verificar se já existe projeto
    log("\n🔍 Verificando projetos existentes...")
    r = requests.get(f"{API}/v1/projects", headers=HEADERS, timeout=10)
    if r.ok:
        projetos = r.json()
        for p in projetos:
            if p["name"] == "gerenciador-planilhas":
                log(f"✅ Projeto já existe: {p['ref']} ({p['status']})")
                return p["ref"]
    
    # 3. Criar projeto
    log("\n🚀 Criando projeto 'gerenciador-planilhas'...")
    log("   (aguarde ~2 minutos)")
    
    body = {
        "organization_id": org_id,
        "name": "gerenciador-planilhas",
        "plan": "free",
        "region": "us-east-1",
        "db_pass": "e90DkuzSVdpgJlc6",
    }
    
    r = requests.post(f"{API}/v1/projects", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        erro = r.json()
        log(f"❌ Erro ao criar: {erro.get('message', r.text[:300])}")
        sys.exit(1)
    
    data = r.json()
    ref = data["ref"]
    log(f"✅ Projeto criado! Ref: {ref}")
    log(f"   Status: {data['status']}")
    
    # 4. Aguardar projeto ficar ativo
    log("\n⏳ Aguardando projeto ficar ativo...")
    for i in range(60):  # 10 minutos max
        time.sleep(10)
        r = requests.get(f"{API}/v1/projects/{ref}", headers=HEADERS, timeout=10)
        if r.ok:
            status = r.json().get("status")
            if status == "ACTIVE_HEALTHY":
                log(f"✅ Projeto ativo! ({i*10}s)")
                break
            elif i % 6 == 0:
                log(f"   Status: {status}... ({i*10}s)")
    
    # 5. Executar schema SQL
    log("\n📝 Executando schema SQL...")
    
    schema_sql = """CREATE TABLE IF NOT EXISTS planilhas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    tamanho BIGINT DEFAULT 0,
    tamanho_formatado TEXT DEFAULT '0 B',
    extensao TEXT DEFAULT '',
    ultima_modificacao TIMESTAMPTZ DEFAULT NOW(),
    data_upload TIMESTAMPTZ DEFAULT NOW(),
    descricao TEXT DEFAULT '',
    favorito BOOLEAN DEFAULT FALSE,
    categoria TEXT DEFAULT '',
    tags JSONB DEFAULT '[]'::jsonb,
    abas JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_planilhas_nome ON planilhas (nome);
CREATE INDEX IF NOT EXISTS idx_planilhas_categoria ON planilhas (categoria);
CREATE INDEX IF NOT EXISTS idx_planilhas_favorito ON planilhas (favorito);
CREATE INDEX IF NOT EXISTS idx_planilhas_created_at ON planilhas (created_at DESC);"""
    
    r = requests.post(
        f"{API}/v1/projects/{ref}/database/query",
        headers=HEADERS,
        json={"query": schema_sql},
        timeout=30,
    )
    if r.ok:
        log("✅ Schema SQL executado com sucesso!")
    else:
        log(f"⚠️ Erro ao executar SQL: {r.text[:300]}")
    
    # 6. Criar bucket de storage (via Database SQL, já que Storage API precisa de auth diferente)
    log("\n📦 Criando bucket 'planilhas' via SQL...")
    
    bucket_sql = """
    INSERT INTO storage.buckets (id, name, public) 
    VALUES ('planilhas', 'planilhas', FALSE)
    ON CONFLICT (id) DO NOTHING;
    """
    r = requests.post(
        f"{API}/v1/projects/{ref}/database/query",
        headers=HEADERS,
        json={"query": bucket_sql},
        timeout=10,
    )
    if r.ok or "already exists" in r.text:
        log("✅ Bucket 'planilhas' criado!")
    else:
        log(f"⚠️ Erro ao criar bucket: {r.text[:300]}")
    
    # 7. Obter credenciais da API Settings
    log("\n🔑 Obtendo service_role key...")
    r = requests.get(
        f"{API}/v1/projects/{ref}",
        headers=HEADERS,
        timeout=10,
    )
    if r.ok:
        project_data = r.json()
    
    # Tenta pegar a service_role key do projeto
    r = requests.get(
        f"https://{ref}.supabase.co/rest/v1/",
        headers=HEADERS,
        timeout=10,
    )
    
    # Pega service role key via management API
    r = requests.get(
        f"{API}/v1/projects/{ref}/api-keys",
        headers=HEADERS,
        timeout=10,
    )
    service_key = ""
    anon_key = ""
    if r.ok:
        keys = r.json()
        for k in keys:
            if k.get("name") == "service_role key":
                service_key = k["api_key"]
            if k.get("name") == "anon key":
                anon_key = k["api_key"]
    
    project_url = f"https://{ref}.supabase.co"
    
    log(f"\n{'='*60}")
    log(f"📋 CREDENCIAIS DO SUPABASE")
    log(f"{'='*60}")
    log(f"\nSUPABASE_URL={project_url}")
    log(f"SUPABASE_SERVICE_KEY={service_key}")
    log(f"SUPABASE_BUCKET=planilhas")
    log(f"\n⚠️  Se a SERVICE_KEY estiver vazia, pegue manualmente:")
    log(f"   1. Acesse: https://supabase.com/dashboard/project/{ref}/settings/api")
    log(f"   2. Copie a 'service_role key'")
    log(f"   3. Adicione nas Environment Variables do Render")
    log(f"\nDepois de adicionar no Render, reinicie o app!")
    
    log(f"\n✅ Configuração concluída!")
    return ref


if __name__ == "__main__":
    main()
