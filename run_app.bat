@echo off
:: GDQ Rule Proposer — Inicializacao rapida (Windows)
:: Duplo-clique neste arquivo para iniciar o app.

title GDQ Rule Proposer

echo.
echo   GDQ Rule Proposer
echo   ==================
echo.

:: Verificar se Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERRO] Python nao encontrado.
    echo.
    echo   Instale Python 3.10 ou superior:
    echo   https://www.python.org/downloads/
    echo.
    echo   IMPORTANTE: Marque "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

:: Mudar para o diretorio do script
cd /d "%~dp0"

:: Executar o launcher
python launcher.py %*

:: Se o launcher falhou, manter a janela aberta
if %errorlevel% neq 0 (
    echo.
    echo   O app encerrou com erro. Consulte as mensagens acima.
    echo   Para ajuda: docs\INSTALL_TROUBLESHOOTING.md
    echo.
    pause
)
