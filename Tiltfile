# Oddsmith local dev stack.
#
# The database lives in Supabase, so `tilt up` runs just the app processes: the
# FastAPI backend and the Next.js frontend — with a live dashboard, log
# streaming, and auto-restart. Quality tasks (tests, lint, build) stay in the
# Makefile.
#
#   tilt up                # backend + frontend (DB is Supabase, via DATABASE_URL)
#   tilt up -- --with-db   # also start the local Postgres container
#   tilt down              # stop whatever this Tiltfile started

# --with-db brings back the local docker-compose Postgres, which is only needed
# for the one-off migration into Supabase. It does not repoint the backend:
# DATABASE_URL in .env still decides what the API connects to.
config.define_bool('with-db')
with_db = config.parse().get('with-db', False)

# VIRTUAL_ENV is pinned so uv does not warn about a sibling project's stale env.
venv = os.path.abspath('.venv')

# --- Postgres (opt-in; reuses the existing docker-compose service) --------- #
backend_deps = []
if with_db:
    docker_compose('docker-compose.yml')
    dc_resource('db', labels=['infra'])
    backend_deps = ['db']

# --- Backend: FastAPI on :8137 -------------------------------------------- #
local_resource(
    'backend',
    serve_cmd='uv run --active uvicorn oddsmith.api:app --reload --port 8137',
    serve_env={'VIRTUAL_ENV': venv},
    resource_deps=backend_deps,
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
