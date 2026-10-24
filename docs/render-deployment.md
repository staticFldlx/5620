# Render deployment

This setup serves the React app and Django API from one paid Render Web Service,
with a separate paid Render Postgres database. The browser uses one origin:
`/` for React and `/api/v1/` for the API.

## Before creating paid resources

Push the deployment commit to the public GitHub branch you plan to deploy. The
repository root contains the Dockerfile; leave Render's Root Directory blank.
The Docker build uses Node 22 to build Vite with the real API enabled, then
copies `frontend/dist` into the Python image. Local `.env` files are excluded
from the Docker build context.

## Render setup

1. Create a paid Postgres database with **New > Postgres**. Use the Singapore
   region and copy its **internal** database URL. Keep the web service in the
   same Render workspace and region.
2. Create **New > Web Service > Public Git Repository** with
   `https://github.com/staticFldlx/5620`. Select the branch containing this
   deployment commit. Set Language to **Docker**, Root Directory to blank,
   Dockerfile Path to `./Dockerfile`, Region to **Singapore**, and choose a paid
   compute plan (the smallest is a reasonable starting point for a demo).
3. Add these environment variables before creating the service:

   | Key | Value |
   | --- | --- |
   | `DATABASE_URL` | Internal URL from the Render Postgres database |
   | `DJANGO_SECRET_KEY` | A newly generated, long random secret |
   | `DJANGO_DEBUG` | `false` |
   | `DJANGO_ALLOWED_HOSTS` | The service's exact `<name>.onrender.com` hostname |
   | `LLM_PROVIDER` | `fake` for an offline demo, or `openai` for a reachable provider |

   For real model calls, also set `LLM_BASE_URL`, `LLM_API_KEY`, and
   `LLM_MODEL_DEFAULT` in Render. Never commit credentials or copy the local
   `.env` file into Git. The university VPN-only proxy cannot be reached from
   Render's cloud environment.

   For the official OpenAI API, use `LLM_PROVIDER=openai`,
   `LLM_BASE_URL=https://api.openai.com/v1`, and
   `LLM_MODEL_DEFAULT=gpt-5.4-mini`. Set `LLM_API_KEY` to a key created in
   the OpenAI Platform. `LLM_MODEL_FAST` can use the same model or be left
   unset. The API account needs active billing; the key belongs only in
   Render's environment variables, never in the frontend build or Git.

4. Set Health Check Path to `/`. After the first deploy is Live, check `/`, a
   deep frontend link such as `/s1`, and `/api/v1/docs` on the service URL.
   The Docker start command applies migrations and loads demo data only if it
   has not already been loaded; it does not reset existing database records.

## Updating and persistence

Services created from a public Git repository URL do not auto-deploy. After
each push to the chosen branch, use **Manual Deploy > Deploy latest commit**.
The database preserves records across web service deploys. Uploaded files
written to `MEDIA_ROOT` do not persist on a normal web service filesystem;
add persistent file storage before relying on file uploads.
