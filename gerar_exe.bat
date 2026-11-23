@echo off
setlocal
cd /d "%~dp0"

echo === Verificando Python ===
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python nao encontrado. Instale em python.org e marque "Add Python to PATH".
        pause
        exit /b 1
    )
    set PY=python
)

echo.
echo === Criando ambiente virtual (.venv) ===
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
) else (
    echo Ambiente virtual ja existe, reaproveitando.
)

echo.
echo === Instalando dependencias no ambiente virtual ===
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install pillow pyinstaller
if errorlevel 1 (
    echo Falha ao instalar as dependencias. Verifique a internet.
    pause
    exit /b 1
)

echo.
echo === Gerando o executavel ===
".venv\Scripts\python.exe" -m PyInstaller --onefile --windowed --name PetshopCadastro petshop.py
if errorlevel 1 (
    echo Falha ao gerar o executavel.
    pause
    exit /b 1
)

echo.
echo Pronto! O programa esta em: dist\PetshopCadastro.exe
echo Copie esse arquivo para uma pasta (ex.: C:\PetshopCadastro) e use de la.
pause
