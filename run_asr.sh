export WHISPER_MODEL=tiny                                                                   
export WHISPER_DEVICE=cpu
export WHISPER_COMPUTE_TYPE=int8
export DATABASE_URL=postgresql+psycopg://clipfabric:clipfabric@localhost:5432/clipfabric
export REDIS_URL=redis://localhost:6379/0
export STORAGE_ROOT=$(pwd)/storage
python -m apps.worker_gpu
