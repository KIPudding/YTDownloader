@echo off
title YT Downloader

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Run your python script
python main.py

:: If the program crashes or you type 'exit', this keeps the window open
pause