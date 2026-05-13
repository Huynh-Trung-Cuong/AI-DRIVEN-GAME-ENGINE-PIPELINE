@echo off
title GAME IS RUNNING...
py -3.12 base.py 2> bug.txt
if %errorlevel% neq 0 (echo [!] GAME CRASHED! Xem loi trong bug.txt && timeout /t 3)
exit