# Dataform runner: executes the same `dataform run` used locally, as a Cloud Run job.
# Auth is ADC (the job's service account) via a keyless .df-credentials.json - no key material.
FROM node:20-slim

WORKDIR /app

# Pin the CLI to the 3.x line to match workflow_settings.yaml (dataformCoreVersion 3.0.0).
RUN npm install -g @dataform/cli@^3.0.0

# Dataform project: definitions/, includes/, workflow_settings.yaml
COPY . /app/

# Keyless credentials: projectId + location only -> the CLI falls back to
# Application Default Credentials, i.e. the Cloud Run job's service account.
RUN printf '{"projectId":"ff14-pf-data","location":"us-central1"}' > /app/.df-credentials.json

CMD ["sh", "-c", "dataform compile && dataform run"]
