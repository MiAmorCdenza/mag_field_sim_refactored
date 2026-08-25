@echo off
cd /d C:\Users\Admin\Documents\trae_projects\mag_field_sim
.venv\Scripts\python.exe surrogate\run_phaseA.py b_mlp_B_divpen c_mlp_A
echo BAT_DONE %ERRORLEVEL%
