from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_mode: str = "mock"
    chroma_persist_directory: Path = Field(default=Path("./storage/chroma"))
    chroma_knowledge_collection: str = "meditrust_knowledge"
    chroma_cache_collection: str = "meditrust_response_cache"
    source_manifest_path: Path = Path("./data/source_manifest.json")
    public_data_dir: Path = Path("./data/public")
    synthetic_data_dir: Path = Path("./data/synthetic")
    cache_ttl_seconds: int = 86400
    cache_similarity_threshold: float = 0.88
    retrieval_default_top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
