import os


def get_qdrant_host() -> str:
    return os.environ.get("AEGIS_QDRANT_HOST", "127.0.0.1")


def get_qdrant_port() -> int:
    return int(os.environ.get("AEGIS_QDRANT_PORT", "6333"))


def get_qdrant_vector_size() -> int:
    return int(os.environ.get("AEGIS_VECTOR_SIZE", "768"))


def get_embed_model() -> str:
    return os.environ.get("AEGIS_EMBED_MODEL", "nomic-embed-text")


def get_primary_fast_model() -> str:
    return os.environ.get("AEGIS_FAST_MODEL", "aegis-fast")


def get_primary_deep_model() -> str:
    return os.environ.get("AEGIS_DEEP_MODEL", "aegis-deep")


def get_telegram_bot_token() -> str:
    return os.environ.get(
        "AEGIS_TELEGRAM_BOT_TOKEN",
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    )


def get_telegram_chat_id() -> str:
    return os.environ.get(
        "AEGIS_TELEGRAM_CHAT_ID",
        os.environ.get("TELEGRAM_CHAT_ID", ""),
    )
