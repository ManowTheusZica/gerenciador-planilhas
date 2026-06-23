-- ============================================================
-- Schema do Supabase para o Gerenciador de Planilhas
-- Execute este SQL no SQL Editor do Supabase Dashboard
-- ============================================================

-- Tabela principal de planilhas
CREATE TABLE IF NOT EXISTS planilhas (
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

-- Índices
CREATE INDEX IF NOT EXISTS idx_planilhas_nome ON planilhas (nome);
CREATE INDEX IF NOT EXISTS idx_planilhas_categoria ON planilhas (categoria);
CREATE INDEX IF NOT EXISTS idx_planilhas_favorito ON planilhas (favorito);
CREATE INDEX IF NOT EXISTS idx_planilhas_created_at ON planilhas (created_at DESC);

-- Bucket de storage (criado via API pela app, mas pode ser manual)
-- INSERT INTO storage.buckets (id, name, public) VALUES ('planilhas', 'planilhas', FALSE)
-- ON CONFLICT (id) DO NOTHING;
