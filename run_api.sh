export DATABASE_URL=postgresql+psycopg://clipfabric:clipfabric@localhost:5432/clipfabric
export REDIS_URL=redis://localhost:6379/0
export STORAGE_ROOT=$(pwd)/storage
uvicorn apps.api.main:app --reload
