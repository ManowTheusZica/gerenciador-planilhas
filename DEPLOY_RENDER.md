# 🚀 Deploy do Gerenciador de Planilhas no Render

## ⚠️ Problema Comum

O Render usa um **sistema de arquivos efêmero** - todos os arquivos são perdidos quando o serviço reinicia. Por isso, é **obrigatório** usar o Supabase para armazenamento persistente.

---

## 📋 Passo a Passo Completo

### 1️⃣ Criar Conta no Supabase

1. Acesse: https://supabase.com
2. Clique em **"Start your project"**
3. Faça login com GitHub/Google
4. Clique em **"New Project"**
5. Preencha:
   - **Name**: `gerenciador-planilhas`
   - **Database Password**: (crie uma senha forte)
   - **Region**: Escolha perto de você (ex: US East)
6. Clique em **"Create new project"**
7. Aguarde ~2 minutos até o projeto ficar pronto

### 2️⃣ Configurar Banco de Dados

1. No painel do Supabase, clique em **"SQL Editor"** (ícone de terminal)
2. Clique em **"New query"**
3. Abra o arquivo `schema.sql` do seu projeto local
4. Copie TODO o conteúdo e cole no SQL Editor
5. Clique em **"Run"** ou pressione `Ctrl+Enter`
6. Você deve ver mensagens de sucesso

### 3️⃣ Obter Credenciais do Supabase

1. No painel do Supabase, clique em **"Settings"** (engrenagem)
2. Clique em **"API"**
3. Copie estas informações:
   - **Project URL**: `https://xxxxx.supabase.co`
   - **service_role key** (SECRET): Clique em "Reveal" e copie a chave longa

⚠️ **IMPORTANTE**: Use a **service_role key**, NUNCA a anon key!

### 4️⃣ Configurar no Render

#### Opção A: Via Dashboard (Recomendado)

1. Acesse: https://dashboard.render.com
2. Vá em seu serviço `gerenciador-planilhas`
3. Clique em **"Environment"** na sidebar
4. Adicione estas variáveis:

```env
SUPABASE_URL = https://seu-projeto.supabase.co
SUPABASE_SERVICE_KEY = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_BUCKET = planilhas
FLASK_SECRET = render-secret-key-2026-mude-isso
PORT = 10000
NETLIFY = true
```

5. Clique em **"Save Changes"**
6. O Render vai reiniciar automaticamente

#### Opção B: Via render.yaml

Edite o arquivo `render.yaml` e adicione as variáveis:

```yaml
services:
  - type: web
    name: gerenciador-planilhas
    runtime: python
    region: oregon
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_KEY
        sync: false
      - key: SUPABASE_BUCKET
        value: planilhas
      - key: FLASK_SECRET
        generateValue: true
      - key: PORT
        value: "10000"
      - key: NETLIFY
        value: "true"
```

### 5️⃣ Verificar Funcionamento

1. Após o deploy, acesse sua URL: `https://gerenciador-planilhas.onrender.com`
2. Tente fazer upload de uma planilha
3. Recarregue a página - a planilha deve continuar lá!
4. Verifique no Supabase:
   - **Storage** > Bucket `planilhas` > Arquivos enviados
   - **Table Editor** > Tabela `metadata` > Registros das planilhas

---

## 🔧 Solução de Problemas

### Erro: "Supabase não configurado"

**Causa**: Variáveis de ambiente não estão definidas

**Solução**:
1. Verifique no Render se as variáveis estão configuradas
2. Certifique-se de que `NETLIFY=true` está definido
3. Reinicie o serviço no Render

### Erro: "Bucket não encontrado"

**Causa**: O bucket do Supabase ainda não foi criado

**Solução**:
1. Acesse o Supabase > Storage
2. Clique em **"Create bucket"**
3. Nome: `planilhas`
4. Marque **"Public bucket"**
5. Clique em **"Create bucket"**

### Erro: "Permissão negada"

**Causa**: Usando anon key ao invés de service_role key

**Solução**:
1. No Supabase, vá em Settings > API
2. Use a **service_role key** (não a anon key)
3. Atualize a variável `SUPABASE_SERVICE_KEY` no Render

### Planilhas somem após reiniciar

**Causa**: Ainda usando modo local (arquivos)

**Solução**:
1. Verifique se `NETLIFY=true` está configurado
2. Verifique se as credenciais do Supabase estão corretas
3. Reinicie o serviço

---

## 💡 Dicas

1. **Backup Automático**: O Supabase faz backup automático dos dados
2. **Escalabilidade**: Supabase suporta projetos grandes sem custo adicional
3. **Colaboração**: Múltiplos usuários podem acessar simultaneamente
4. **Segurança**: As chaves ficam seguras no painel do Render

---

## 📞 Suporte

Se tiver problemas:
1. Verifique os logs no Render: Dashboard > Seu Serviço > Logs
2. Verifique os logs no Supabase: Dashboard > Logs
3. Consulte a documentação: https://render.com/docs

---

**Pronto! Seu gerenciador de planilhas agora funciona perfeitamente no Render!** 🎉
