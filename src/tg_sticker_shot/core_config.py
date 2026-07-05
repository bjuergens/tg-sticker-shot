"""Config/secrets via environment variables (pydantic-settings). Never in the repo.

Settings are instantiated only where actually needed (e.g. when the gemini
backend is selected), so offline/fake usage requires no environment.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash-image", alias="GEMINI_MODEL")
    # Text-out vision model for `shot review` (not project-locked — it never
    # generates images, so it cannot affect image consistency).
    gemini_review_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_REVIEW_MODEL")
