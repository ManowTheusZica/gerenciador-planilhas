# 📊 Gerenciador de Planilhas v2.0

Sistema web avançado para gerenciar, organizar e colaborar em planilhas Excel, CSV e ODS com recursos de edição em tempo real, versionamento automático e busca full-text.

## ✨ Funcionalidades Principais

### 🚀 Core
- **Upload múltiplo**: Arraste vários arquivos simultaneamente
- **Validação MIME**: Verificação real do tipo de arquivo (não apenas extensão)
- **Preview inteligente**: Visualize dados antes de abrir
- **Busca full-text**: Encontre conteúdo dentro das células das planilhas
- **Categorização**: Organize por tags e categorias personalizadas

### 🔒 Segurança & Confiabilidade
- **Backup automático**: Snapshots antes de cada modificação
- **Versionamento**: Histórico completo com rollback para versões anteriores
- **Validação de dados**: Detecta duplicatas, células vazias, tipos mistos
- **Tratamento de erros robusto**: Logging detalhado e recovery automático

### 👥 Colaboração em Tempo Real
- **Edição colaborativa**: Múltiplos usuários editando simultaneamente
- **Locks inteligentes**: Evita conflitos de edição
- **Chat integrado**: Comunicação entre colaboradores
- **Cursor tracking**: Veja onde outros usuários estão editando
- **Notificações em tempo real**: Alertas instantâneos via WebSocket

### 📈 Análise & Exportação
- **Dashboard analítico**: Estatísticas detalhadas de uso
- **Exportação multi-formato**: Excel, CSV, PDF com formatação
- **Compressão automática**: Otimiza arquivos grandes (>10MB)
- **Relatórios personalizados**: Filtros e agrupamentos avançados

### 🔔 Notificações
- **Sistema completo**: Uploads, deleções, atualizações, erros
- **Histórico persistente**: Últimas 100 notificações salvas
- **Real-time**: Via WebSocket para usuários conectados

## 🏗️ Arquitetura

```
gerenciador-planilhas/
├── app.py                    # Aplicação Flask principal + Socket.IO
├── supabase_client.py        # Cliente Supabase (banco + storage)
├── requirements.txt          # Dependências Python
├── schema.sql               # Schema do banco Supabase
├── netlify.toml             # Configuração Netlify
├── runtime.txt              # Versão Python para deploy
├── _redirects               # Redirects Netlify
├── .env.example            # Exemplo de variáveis de ambiente
├── uploads/                # Arquivos locais (modo local)
├── backups/                # Backups automáticos
├── versions/               # Versionamento de planilhas
├── indice_busca/           # Índice Whoosh para busca full-text
├── notificacoes.json       # Cache de notificações
├── metadata.json           # Metadados locais (modo local)
├── static/
│   └── styles.css          # Estilos CSS customizados
├── templates/
│   └── index.html          # Interface web única (SPA-like)
└── netlify/
    └── functions/
        ├── api.py          # Funções serverless Netlify
        └── hello.py        # Health check
```

## 🚀 Instalação

### Pré-requisitos
- Python 3.8+
- pip (gerenciador de pacotes)
- (Opcional) Conta Supabase para modo cloud

### Modo Local (Rápido)

1. Clone ou copie os arquivos
2. Instale dependências:
```bash
pip install -r requirements.txt
```

3. Execute:
```bash
python app.py
```

4. Acesse: http://localhost:5000

### Modo Cloud (Netlify + Supabase)

1. Crie projeto no [Supabase](https://supabase.com)
2. Execute o schema SQL (`schema.sql`)
3. Configure variáveis de ambiente no Netlify:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `SUPABASE_BUCKET` (opcional, default: 'planilhas')

4. Deploy no Netlify (conecte repositório GitHub)

## ⚙️ Configuração

### Variáveis de Ambiente

```env
# Supabase (para modo cloud)
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_KEY=sua_service_role_key_aqui
SUPABASE_BUCKET=planilhas

# Flask
FLASK_SECRET=sua_chave_secreta_aleatoria
PORT=5000

# Netlify
NETLIFY=true
```

### Schema do Banco

Execute em seu projeto Supabase:

```sql
-- Tabela de planilhas
CREATE TABLE planilhas (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  nome TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  tamanho BIGINT,
  tamanho_formatado TEXT,
  extensao TEXT,
  ultima_modificacao TIMESTAMPTZ,
  data_upload TIMESTAMPTZ DEFAULT NOW(),
  descricao TEXT,
  favorito BOOLEAN DEFAULT FALSE,
  categoria TEXT,
  tags JSONB DEFAULT '[]',
  abas JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_planilhas_favorito ON planilhas(favorito DESC);
CREATE INDEX idx_planilhas_nome ON planilhas(nome);
CREATE INDEX idx_planilhas_categoria ON planilhas(categoria);
CREATE INDEX idx_planilhas_data ON planilhas(ultima_modificacao DESC);
```

## 📖 Uso

### Upload de Planilhas
1. Clique em "Upload" ou arraste arquivos
2. Formatos suportados: `.xlsx`, `.xls`, `.xlsm`, `.csv`, `.ods`
3. Validação automática de tipo MIME
4. Backup criado automaticamente

### Busca Avançada
- **Busca simples**: Por nome, tags, categoria
- **Busca full-text**: Encontra texto dentro das células
- Use a barra de pesquisa no topo

### Edição Colaborativa
1. Abra uma planilha
2. Clique em "Modo Colaborativo"
3. Outros usuários podem entrar na mesma sala
4. Locks previnem edições conflitantes
5. Chat integrado para comunicação

### Versionamento
- Cada modificação cria uma versão automática
- Acesse via menu "Versões" na planilha
- Rollback com um clique para qualquer versão anterior
- Mantém últimas 20 versões por planilha

### Exportação
- **Excel (.xlsx)**: Formato original
- **CSV**: Para integração com outros sistemas
- **PDF**: Relatórios formatados (limitado a 100 linhas)

### Validação de Dados
1. Selecione uma planilha
2. Clique em "Validar Dados"
3. Sistema verifica:
   - Células vazias
   - Linhas duplicadas
   - Tipos inconsistentes
   - Tamanho excessivo

### Compressão
- Automática para arquivos >10MB
- Remove formatação desnecessária
- Mantém dados intactos
- Redução típica: 10-30%

## 🔧 APIs Disponíveis

### Upload
```http
POST /api/upload
Content-Type: multipart/form-data

files=<arquivo1>&files=<arquivo2>
```

### Listar Planilhas
```http
GET /api/planilhas
```

### Download
```http
GET /api/planilhas/{id}/download
```

### Preview
```http
GET /api/planilhas/{id}/preview?sheet=Sheet1&limite=50
```

### Busca Full-Text
```http
GET /api/buscar-fulltext?q=termo+de+busca
```

### Exportar
```http
GET /api/planilhas/{id}/exportar?formato=csv&sheet=Sheet1
```

### Validar
```http
GET /api/planilhas/{id}/validar
```

### Comprimir
```http
POST /api/planilhas/{id}/comprimir
```

### Versionamento
```http
GET /api/planilhas/{id}/versoes
POST /api/planilhas/{id}/restaurar/{version_id}
```

### Notificações
```http
GET /api/notificacoes
POST /api/notificacoes/marcar-lida
POST /api/notificacoes/limpar
```

### Estatísticas
```http
GET /api/stats
```

## 🔌 Eventos Socket.IO

### Conexão
```javascript
socket.emit('connect')
socket.on('status', (data) => console.log(data.msg))
```

### Entrar em Sala
```javascript
socket.emit('join_planilha', {
  planilha_id: 'abc123',
  user: 'João Silva'
})
```

### Solicitar Lock
```javascript
socket.emit('request_lock', {
  planilha_id: 'abc123',
  sheet: 'Sheet1',
  user: 'João Silva'
})
```

### Editar Célula
```javascript
socket.emit('cell_edit', {
  planilha_id: 'abc123',
  sheet: 'Sheet1',
  row: 5,
  col: 3,
  value: 'Novo Valor',
  user: 'João Silva'
})
```

### Chat
```javascript
socket.emit('chat_message', {
  planilha_id: 'abc123',
  user: 'João Silva',
  message: 'Alguém pode revisar esta célula?'
})
```

## 🛡️ Segurança

- **Validação MIME**: Previne upload de arquivos maliciosos
- **Sanitização**: Inputs validados e sanitizados
- **Autenticação Supabase**: Service role key para operações seguras
- **Backups automáticos**: Recovery em caso de erro
- **Locks de edição**: Previne corrupção de dados

## 📊 Performance

- **Lazy loading**: Carrega apenas dados visíveis
- **Cache inteligente**: Planilhas em memória para edição rápida
- **Indexação Whoosh**: Busca full-text otimizada
- **Paginação**: Preview limitado a 200 linhas
- **Compressão**: Arquivos otimizados automaticamente

## 🐛 Troubleshooting

### Erro ao conectar ao Supabase
- Verifique se `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` estão corretos
- Use service_role key, não anon key
- Teste conexão: `python -c "import supabase_client; print(supabase_client.get_client())"`

### Busca full-text não funciona
- Instale Whoosh: `pip install whoosh`
- Reindexe planilhas existentes

### Erro na exportação PDF
- Instale reportlab: `pip install reportlab`
- Limitação: máximo 100 linhas por aba

### Colaboração não sincroniza
- Verifique conexão WebSocket
- Firewall pode bloquear porta do Socket.IO
- Use HTTPS em produção

### Arquivos muito lentos para carregar
- Use compressão automática
- Considere dividir planilhas muito grandes
- Limite preview a menos linhas

## 🚀 Deploy em Produção

### Netlify (Recomendado)
1. Conecte repositório GitHub
2. Configure variáveis de ambiente
3. Build command: `pip install -r requirements.txt`
4. Publish directory: `/`
5. Functions: `netlify/functions`

### Heroku
```bash
heroku create meu-gerenciador
heroku config:set SUPABASE_URL=...
heroku config:set SUPABASE_SERVICE_KEY=...
git push heroku main
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "app:app"]
```

## 📝 Changelog

Veja [CHANGELOG.md](CHANGELOG.md) para histórico completo de versões.

## 🤝 Contribuindo

1. Fork o projeto
2. Crie branch para feature: `git checkout -b feature/nova-funcionalidade`
3. Commit mudanças: `git commit -m 'Adiciona nova funcionalidade'`
4. Push: `git push origin feature/nova-funcionalidade`
5. Abra Pull Request

## 📄 Licença

Este projeto é de uso interno do Detran. Não distribuir sem autorização.

## 👥 Suporte

Para dúvidas ou problemas:
- Logs: Verifique `logs/` (se configurado)
- Issues: Abra issue no repositório
- Email: Equipe de TI do Detran

---

**Versão**: 2.0  
**Última atualização**: Junho 2026  
**Status**: ✅ Produção Ready
