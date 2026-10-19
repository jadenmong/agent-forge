FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY examples ./examples
RUN python -m pip install --no-cache-dir -e .
ENV AGENTFORGE_DB_PATH=/data/demo.db
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "agentforge.api:app", "--host", "0.0.0.0", "--port", "8000"]
