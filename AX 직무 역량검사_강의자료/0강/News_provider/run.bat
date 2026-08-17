@echo off
REM 일일 뉴스 브리핑 실행 래퍼 (Windows 작업 스케줄러용)
cd /d C:\Git\News_provider
C:\Python314\python.exe -X utf8 -m newsbrief.main >> logs\run.log 2>&1
