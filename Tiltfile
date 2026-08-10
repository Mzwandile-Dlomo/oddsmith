# Oddsmith local dev stack.
#
# `tilt up` runs the whole app: Postgres (via docker-compose), the FastAPI
# backend, and the Next.js frontend — with a live dashboard, log streaming, and
# auto-restart. Quality tasks (tests, lint, build) stay in the Makefile.
#
#   tilt up      # start everything + open the dashboard
#   tilt down    # stop the app processes and the Postgres container

# VIRTUAL_ENV is pinned so uv does not warn about a sibling project's stale env.
venv = os.path.abspath('.venv')

# --- Postgres (reuses the existing docker-compose service) ---------------- #
docker_compose('docker-compose.yml')
dc_resource('db', labels=['infra'])

# --- Backend: FastAPI on :8137 -------------------------------------------- #
local_resource(
    'backend',
    serve_cmd='uv run --active uvicorn oddsmith.api:app --reload --port 8137',
    serve_env={'VIRTUAL_ENV': venv},
    resource_deps=['db'],
    readiness_probe=probe(
        http_get=http_get_action(port=8137, path='/health'),
        initial_delay_secs=2,
        period_secs=3,
    ),
    links=[link('http://localhost:8137/docs', 'API docs')],
    labels=['app'],
)

# --- Frontend: Next.js on :3000 ------------------------------------------- #
local_resource(
    'frontend',
    serve_cmd='npm run dev',
    serve_dir='web',
    resource_deps=['backend'],
    readiness_probe=probe(
        http_get=http_get_action(port=3000, path='/'),
        initial_delay_secs=3,
        period_secs=3,
    ),
    links=[link('http://localhost:3000', 'Oddsmith web')],
    labels=['app'],
)
