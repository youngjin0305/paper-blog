@echo off
setlocal
cd /d "%~dp0"
if not exist "node_modules\@google\gemini-cli\bundle\gemini.js" (
  call npm.cmd ci --no-audit --no-fund
  if errorlevel 1 goto fail
)
echo Select "Sign in with Google" and use your student AI Pro account.
echo After signing in, enter /quit and return to Paper Garden.
set "GEMINI_CLI_SYSTEM_SETTINGS_PATH=%~dp0policies\cli-settings.json"
set "GEMINI_API_KEY="
set "GOOGLE_API_KEY="
set "GOOGLE_GENAI_USE_VERTEXAI="
node node_modules\@google\gemini-cli\bundle\gemini.js
if errorlevel 1 goto fail
exit /b %errorlevel%
:fail
echo Gemini CLI setup failed. Node.js 20+ is required.
pause
exit /b 1
