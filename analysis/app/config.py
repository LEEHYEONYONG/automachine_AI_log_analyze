import os

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

OLLAMA_URL = os.getenv("OLLAMA_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct-q4_K_M")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# Only logs/ is mounted into this container. ground_truth/ is for eval/ only.
LOGS_DIR = os.getenv("LOGS_DIR", "/logs")
