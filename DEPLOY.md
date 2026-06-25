# 🚀 Guia de Deploy - Gerenciador de Planilhas v2.0

## Opções de Deploy

### 1. Render.com (Recomendado)

O Render é ideal para aplicações Flask com WebSocket.

#### Passos:

1. **Crie uma conta** em https://render.com

2. **Conecte seu repositório GitHub** ou faça upload manual

3. **Crie um novo Web Service**:
   - Nome: `gerenciador-planilhas`
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --worker-class eventlet -w 1`

4. **Configure Variáveis de Ambiente**:
   ```
   FLASK_SECRET=<gerar_chave_aleatoria>
   SUPABASE_URL=https://seu-projeto.supabase.co
   SUPABASE_SERVICE_KEY=sua_service_role_key
   SUPABASE_BUCKET=planilhas
   ```

5. **Deploy Automático**:
   - O Render detecta o arquivo `render.yaml`
   - Cada push para o branch principal faz deploy automático

6. **Acesse**: `https://gerenciador-planilhas.onrender.com`

---

### 2. Heroku

#### Passos:

1. **Instale Heroku CLI**: https://devcenter.heroku.com/articles/heroku-cli

2. **Login**:
   ```bash
   heroku login
   ```

3. **Crie o app**:
   ```bash
   cd gerenciador-planilhas
   heroku create seu-gerenciador-planilhas
   ```

4. **Configure variáveis**:
   ```bash
   heroku config:set FLASK_SECRET=sua_chave_secreta
   heroku config:set SUPABASE_URL=https://seu-projeto.supabase.co
   heroku config:set SUPABASE_SERVICE_KEY=sua_key
   heroku config:set SUPABASE_BUCKET=planilhas
   ```

5. **Deploy**:
   ```bash
   git add .
   git commit -m "Deploy inicial"
   git push heroku main
   ```

6. **Acesse**: `https://seu-gerenciador-planilhas.herokuapp.com`

---

### 3. Railway.app

#### Passos:

1. **Crie conta** em https://railway.app

2. **New Project** → **Deploy from GitHub repo**

3. **Configure Variables**:
   - `FLASK_SECRET`: chave aleatória
   - `SUPABASE_URL`: URL do Supabase
   - `SUPABASE_SERVICE_KEY`: sua key
   - `PORT`: Railway define automaticamente

4. **Deploy automático** ao fazer push

---

### 4. PythonAnywhere (Gratuito)

#### Passos:

1. **Crie conta** em https://www.pythonanywhere.com

2. **Upload dos arquivos** via Git ou interface web

3. **Configure Web App**:
   - Framework: Flask
   - Python version: 3.11
   - Source code: `/home/seuusuario/gerenciador-planilhas`
   - Working directory: `/home/seuusuario/gerenciador-planilhas`

4. **WSGI Configuration**:
   Edite o arquivo WSGI para:
   ```python
   import sys
   path = '/home/seuusuario/gerenciador-planilhas'
   if path not in sys.path:
       sys.path.append(path)
   
   from app import app as application
   ```

5. **Reload** o web app

---

### 5. VPS Próprio (DigitalOcean, AWS, etc.)

#### Usando Docker:

1. **Crie Dockerfile**:
   ```dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   COPY . .
   
   EXPOSE 5000
   
   CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--worker-class", "eventlet", "-w", "1"]
   ```

2. **Build e Run**:
   ```bash
   docker build -t gerenciador-planilhas .
   docker run -d -p 5000:5000 \
     -e FLASK_SECRET=sua_chave \
     -e SUPABASE_URL=https://... \
     -e SUPABASE_SERVICE_KEY=... \
     gerenciador-planilhas
   ```

#### Usando systemd (Linux):

1. **Crie serviço**:
   ```bash
   sudo nano /etc/systemd/system/gerenciador-planilhas.service
   ```

2. **Conteúdo**:
   ```ini
   [Unit]
   Description=Gerenciador de Planilhas
   After=network.target
   
   [Service]
   User=www-data
   WorkingDirectory=/opt/gerenciador-planilhas
   Environment="PATH=/opt/gerenciador-planilhas/venv/bin"
   ExecStart=/opt/gerenciador-planilhas/venv/bin/gunicorn app:app --bind 0.0.0.0:5000 --worker-class eventlet -w 1
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

3. **Inicie**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start gerenciador-planilhas
   sudo systemctl enable gerenciador-planilhas
   ```

---

## Configuração do Supabase

Antes de qualquer deploy, configure o Supabase:

1. **Crie projeto** em https://supabase.com

2. **Execute schema.sql** no SQL Editor

3. **Pegue as credenciais**:
   - Project URL: `https://xxxxx.supabase.co`
   - Service Role Key: Settings → API → service_role key

4. **Configure Storage Bucket**:
   - Vá em Storage
   - Crie bucket chamado `planilhas`
   - Configure permissões RLS se necessário

---

## Variáveis de Ambiente Obrigatórias

```env
# Flask
FLASK_SECRET=chave_secreta_aleatoria_muito_longa

# Supabase (obrigatório para modo cloud)
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_BUCKET=planilhas

# Opcional
PORT=5000  # A maioria dos hosts define automaticamente
```

---

## Pós-Deploy

1. **Teste o acesso**: Abra a URL no navegador
2. **Verifique logs**: 
   - Render: Dashboard → Logs
   - Heroku: `heroku logs --tail`
   - Railway: Dashboard → Deployments → Logs
3. **Teste upload**: Faça upload de uma planilha teste
4. **Teste WebSocket**: Abra colaboração em tempo real
5. **Configure domínio customizado** (opcional)

---

## Troubleshooting

### Erro: ModuleNotFoundError
- Verifique se todas as dependências estão no `requirements.txt`
- Execute: `pip install -r requirements.txt`

### Erro: Supabase não configurado
- Verifique variáveis de ambiente no painel do host
- Use `SUPABASE_SERVICE_KEY`, não anon key

### WebSocket não conecta
- Verifique se `eventlet` está instalado
- Use `--worker-class eventlet` no Gunicorn
- Configure CORS corretamente

### Arquivos muito grandes
- Aumente `MAX_CONTENT_LENGTH` no app.py
- Configure timeout do host (Render: 5min gratuito)

---

## Domínio Customizado

### Render:
1. Settings → Custom Domain
2. Adicione seu domínio
3. Configure DNS CNAME para `seu-app.onrender.com`

### Heroku:
```bash
heroku domains:add www.seudominio.com
```

### Railway:
1. Settings → Domains
2. Add Custom Domain
3. Configure DNS

---

## Monitoramento

### Health Check:
Adicione rota em `app.py`:
```python
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200
```

### Logs:
- Render: Dashboard → Logs
- Heroku: `heroku logs --tail`
- Railway: Dashboard → Logs

### Métricas:
Considere adicionar:
- Sentry para error tracking
- New Relic para performance
- UptimeRobot para monitoramento

---

**Dica**: Comece com Render (gratuito) e migre para pago se precisar de mais recursos!
