@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Категорийная аналитика РТГ
echo.
echo   КАТЕГОРИЙНАЯ АНАЛИТИКА РТГ
echo   ==========================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo   ОШИБКА: Python не установлен.
  echo   Скачайте с python.org, при установке отметьте "Add Python to PATH".
  echo.
  pause
  exit /b 1
)
echo   Проверяю библиотеки...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
echo.
python engine\run.py %*
echo.
if errorlevel 1 (
  echo   Расчёт завершился с ошибкой. Текст выше.
) else (
  echo   Готово. Отчёты в папке 3_ОТЧЁТЫ.
  for /f "delims=" %%d in ('dir /b /ad /o-d "3_ОТЧЁТЫ"') do (
    start "" "3_ОТЧЁТЫ\%%d"
    goto :конец
  )
)
:конец
echo.
pause
