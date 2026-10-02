@echo off
REM doc-ocr for Windows — runs the unified CLI with the venv Python if present.
set "HERE=%~dp0"
if exist "%HERE%venv\Scripts\python.exe" (
    "%HERE%venv\Scripts\python.exe" "%HERE%doc-ocr" %*
) else (
    python "%HERE%doc-ocr" %*
)
