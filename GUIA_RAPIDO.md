# 🚀 Guia Rápido - Gerenciador de Planilhas v2.0

## Configuração em 5 Minutos

### 1. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 2. Executar (Modo Local)
```bash
python app.py
```
Acesse: http://localhost:5000

### 3. Ou Configurar Supabase (Modo Cloud)
- Crie projeto em https://supabase.com
- Execute `schema.sql` no SQL Editor
- Configure variáveis no `.env`:
  ```env
  SUPABASE_URL=https://seu-projeto.supabase.co
  SUPABASE_SERVICE_KEY=sua_key_aqui
  ```

---

## Funcionalidades Principais

### 📤 Upload de Planilhas
1. Clique em "Upload" ou arraste arquivos
2. Formatos: `.xlsx`, `.xls`, `.xlsm`, `.csv`, `.ods`
3. Validação automática de tipo MIME
4. Backup criado automaticamente

### 🔍 Busca Avançada
- **Simples**: Digite na barra de pesquisa
- **Full-text**: Encontra texto dentro das células
- Filtre por tags, categorias, favoritos

### 👥 Colaboração em Tempo Real
1. Abra uma planilha
2. Clique em "Modo Colaborativo"
3. Compartilhe o link com colegas
4. Locks automáticos previnem conflitos
5. Use o chat integrado para comunicar

### 📊 Versionamento
- Cada alteração cria versão automática
- Acesse via menu "Versões"
- Rollback com um clique
- Mantém últimas 20 versões

### 📈 Validação de Dados
1. Selecione planilha
2. Clique em "Validar Dados"
3. Sistema verifica:
   - ✅ Células vazias
   - ✅ Linhas duplicadas
   - ✅ Tipos inconsistentes
   - ✅ Tamanho excessivo

### 💾 Exportação
- **Excel**: Formato original
- **CSV**: Para integração
- **PDF**: Relatórios formatados

### 🔔 Notificações
- Alertas em tempo real
- Uploads, deleções, erros
- Histórico das últimas 100

### 🗜️ Compressão
- Automática para arquivos >10MB
- Remove formatação desnecessária
- Redução típica: 10-30%

---

## Atalhos Úteis

| Ação | Como Fazer |
|------|------------|
| Upload rápido | Arraste arquivo para a janela |
| Buscar conteúdo | Digite na barra superior |
| Favoritar | Clique na estrela ⭐ |
| Categorizar | Menu lateral → Tags |
| Exportar | Botão "Exportar" na planilha |
| Validar | Botão "Validar Dados" |
| Ver versões | Menu "Histórico" |
| Comprimir | Botão "Otimizar" se >10MB |

---

## Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Erro no upload | Verifique formato do arquivo |
| Busca não funciona | Instale: `pip install whoosh` |
| PDF não exporta | Instale: `pip install reportlab` |
| Colaboração falha | Verifique conexão WebSocket |
| Arquivo lento | Use compressão automática |

---

## Próximos Passos

1. ✅ Faça upload da primeira planilha
2. ✅ Teste busca full-text
3. ✅ Experimente colaboração
4. ✅ Configure versionamento
5. ✅ Explore dashboard analítico

Para mais detalhes, consulte o [README.md](README.md) completo.

---

**Dica Pro**: Use tags e categorias para organizar centenas de planilhas!
