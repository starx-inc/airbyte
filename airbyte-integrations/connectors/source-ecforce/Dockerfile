FROM python:3.12-slim

# Bash is installed for more convenient debugging.
RUN apt-get update && apt-get install -y bash && rm -rf /var/lib/apt/lists/*

WORKDIR /airbyte/integration_code
COPY source_ecforce ./source_ecforce
COPY main.py ./
COPY pyproject.toml ./
COPY poetry.lock ./
COPY README.md ./

# Install poetry
RUN pip install poetry

# Configure poetry to not use virtual environments
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only main

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.1.0
LABEL io.airbyte.name=airbyte/source-ecforce
