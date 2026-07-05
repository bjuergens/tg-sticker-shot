"""Config/secrets via environment variables (pydantic-settings). Never in the repo.

Settings are instantiated only where actually needed (e.g. when the gemini
backend is selected), so offline/fake usage requires no environment.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash-image", alias="GEMINI_MODEL")
