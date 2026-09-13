@echo off
chcp 866 >nul
cd /d "%~dp0"
title Obnovit sayt RTG
echo.
echo   ==========================================
echo     ВЫЛОЖИТЬ ОТЧЁТЫ И ОБНОВИТЬ ССЫЛКУ
echo   ==========================================
echo.
echo   Будут отправлены только папки 3_ОТЧЁТЫ и docs.
echo   Исходные выгрузки НЕ отправляются.
echo.
echo   Ссылка на дашборд:
echo   https://kryukovdaniiljob-cell.github.io/RTG/
echo.
echo   Нажмите любую клавишу, чтобы отправить.
echo   Чтобы отменить - просто закройте это окно.
echo.
pause
echo.
where git >nul 2>nul
if errorlevel 1 goto nogit
git add "3_ОТЧЁТЫ" docs "база"
git diff --staged --quiet
if not errorlevel 1 goto nochanges
git commit -q -m "Otchety za %DATE%"
if errorlevel 1 goto failed
git pull --rebase --autostash
git push
if errorlevel 1 goto failed
echo.
echo   Отправлено. Ссылка обновится за 1-2 минуты:
echo   https://kryukovdaniiljob-cell.github.io/RTG/
goto done

:nochanges
echo.
echo   Новых отчётов нет - отправлять нечего.
goto done

:nogit
echo.
echo   ОШИБКА: git не установлен. Скачайте с git-scm.com
goto done

:failed
echo.
echo   Не удалось отправить. Текст ошибки выше.
goto done

:done
echo.
pause
