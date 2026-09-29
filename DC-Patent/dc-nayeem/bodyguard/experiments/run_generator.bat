@echo off
cd /d e:\DC-Patent\dc-nayeem\bodyguard
python experiments\generate_csv_standalone.py > experiments\output\generation_log.txt 2>&1
echo DONE (exit code: %ERRORLEVEL%) >> experiments\output\generation_log.txt
