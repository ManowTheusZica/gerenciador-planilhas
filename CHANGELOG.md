# Changelog - Gerenciador de Planilhas

Todas as mudanças notáveis neste projeto.

## [2.0.0] - 2026-06-25

### 🚀 Adicionado
- **Validação MIME real**: Verificação do tipo real do arquivo, não apenas extensão
- **Backup automático**: Snapshots antes de cada modificação (upload, update, delete)
- **Versionamento completo**: Histórico de versões com rollback para qualquer ponto anterior
- **Busca full-text**: Indexação Whoosh para buscar texto dentro das células das planilhas
- **Exportação avançada**: Suporte a CSV, PDF (com reportlab), Excel otimizado
- **Compressão automática**: Otimiza arquivos >10MB removendo formatação desnecessária
- **Validação de dados**: Detecta duplicatas, células vazias, tipos inconsistentes
- **Sistema de notificações**: Alertas em tempo real via WebSocket + persistência JSON
- **Colaboração completa**: Locks inteligentes, chat integrado, cursor tracking
- **Dashboard analítico**: Estatísticas detalhadas de uso, tags, categorias
- **Tratamento de erros robusto**: Logging detalhado com exc_info, recovery automático

### 🔒 Segurança
- Validação MIME type previne upload de arquivos maliciosos
- Sanitização de inputs em todas as rotas
- Service role key do Supabase (não anon)
- Backups automáticos antes de operações destrutivas

### 👥 Colaboração em Tempo Real
- Sistema de locks por planilha
- Chat integrado na sala de edição
- Tracking de cursores dos usuários
- Notificações de entrada/saída de usuários
- Sincronização de edições de células via WebSocket

### 📈 Performance
- Lazy loading para planilhas grandes
- Cache inteligente em memória
- Indexação Whoosh para busca rápida
- Paginação automática de previews
- Compressão de arquivos grandes

### 📦 Dependências Novas
- `reportlab>=4.0` - Exportação PDF
- `whoosh>=2.7` - Busca full-text
- `pillow>=10.0` - Processamento de imagens (futuro)

### 🐛 Corrigido
- Erros silenciosos agora logados com stack trace completo
- Upload de arquivos corrompidos bloqueado
- Memory leaks no cache de planilhas
- Race conditions em operações concorrentes

### ♻️ Refatorado
- Código modularizado em funções menores
- Separação clara entre modo local e Supabase
- Logging centralizado e estruturado
- Tratamento de exceções padronizado

---

## [1.0.0] - Versão Inicial

### Funcionalidades Básicas
- Upload de planilhas Excel, CSV, ODS
- Visualização em preview
- Categorização por tags
- Busca simples por nome
- Download de arquivos
- Modo local (arquivos + JSON)
- Modo cloud (Supabase)
- Socket.IO básico configurado
