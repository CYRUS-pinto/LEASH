@echo off
setlocal

set PYTHON=python

if "%1"=="" goto test
if "%1"=="test" goto test
if "%1"=="eval" goto eval
if "%1"=="demo" goto demo
if "%1"=="seed" goto seed
if "%1"=="verify-audit" goto verify_audit
if "%1"=="anchor" goto anchor
if "%1"=="clean" goto clean
goto usage

:seed
%PYTHON% -m leash.db
goto end

:test
%PYTHON% -m leash.db
%PYTHON% -m pytest -v tests/
goto end

:eval
%PYTHON% -m leash.db
%PYTHON% -m eval.harness
goto end

:demo
%PYTHON% -m leash.db
%PYTHON% run_demo.py
goto end

:verify_audit
%PYTHON% leash_cli.py verify-audit
goto end

:anchor
%PYTHON% leash_cli.py anchor
goto end

:clean
if exist data\*.db del /Q data\*.db
goto end

:usage
echo Usage: make [seed ^| test ^| eval ^| demo ^| verify-audit ^| anchor ^| clean]
exit /b 1

:end
exit /b %ERRORLEVEL%
