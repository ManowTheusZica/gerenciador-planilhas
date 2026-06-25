@echo off
title Gerenciador de Planilhas v2.0
color 0A
cls
echo ========================================
echo   Gerenciador de Planilhas v2.0
echo ========================================
echo.
echo  Recursos:
echo    - Upload com validacao MIME
echo    - Busca full-text no conteudo
echo    - Colaboracao em tempo real
echo    - Versionamento automatico
echo    - Exportacao CSV/PDF/Excel
echo    - Validacao de dados
echo    - Compressao automatica
echo    - Notificacoes em tempo real
echo.
echo  Iniciando servidor...
echo.
echo  Acesse no navegador:
echo    http://localhost:5000
echo.
echo  Para COMPARTILHAR na rede:
echo    http://10.138.6.24:5000
echo.
echo ========================================
echo.

cd /d "%~dp0"
"C:\Users\matheus.mendes\Documents\Detran\.venv\Scripts\python.exe" app.py

pause
