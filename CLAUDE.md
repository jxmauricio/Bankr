# Bankr

## Restart dev servers after changes that need it

Dev servers are defined in `.claude/launch.json`. Start or restart them with the preview tools (`preview_start` / `preview_stop`), never with Bash. Restart only servers that are already running, and only for changes that need it. Say in your reply which servers you restarted.

`preview_list` shows only this chat's servers, so an empty list doesn't mean nothing is running. Check the ports too (`lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8000|8010|5173|5183)\b'`). If a server that needs a restart belongs to another chat, `preview_stop` can't stop it. Ask the user before taking it over. To take it over, kill the process listening on the port, wait for the port to free up, then `preview_start` it from this chat.

**Backend** (`backend`, and `backend-verify` if it's running): uvicorn runs **without `--reload`**, so it keeps serving old code. Restart it after:
- any change under `backend/app/` (Python code, the agent prompt or tools, the category mapping, config)
- a new Alembic migration (the launch command runs `alembic upgrade head` on start)
- changes to `backend/requirements*.txt`, after installing them into `backend/.venv`
- changes to backend environment variables or `.env`

No restart is needed for test-only changes (`backend/tests/`).

**Frontend** (`web`, `web-verify`, `web-ngrok`): Vite hot-reloads `web/src/`, so ordinary component, style and TypeScript edits need no restart. Restart it after:
- changes to `web/vite.config.ts`, `web/index.html`, `web/tsconfig*.json`
- changes to `web/package.json` dependencies, after running `npm install`
- changes to `VITE_*` or other environment variables, or `.env` files

After a restart, check `preview_logs` for startup errors before you call the change done.
