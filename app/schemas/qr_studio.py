from typing import Literal

from pydantic import BaseModel, Field

QrKind = Literal["table", "counter"]


class QrDesignConfig(BaseModel):
    primary: str = Field(min_length=7, max_length=7)
    accent: str = Field(min_length=7, max_length=7)
    headline: str = Field(default="", max_length=80)
    tagline: str = Field(default="", max_length=80)
    show_logo: bool = True


class QrTemplateItem(BaseModel):
    id: str
    name: str
    description: str
    defaults: QrDesignConfig


class QrDesignResponse(BaseModel):
    kind: QrKind
    template_id: str
    config: QrDesignConfig
    saved: bool


class QrDesignsResponse(BaseModel):
    table: QrDesignResponse
    counter: QrDesignResponse
    logo_url: str | None


class QrDesignUpdate(BaseModel):
    template_id: str = Field(min_length=1, max_length=32)
    config: QrDesignConfig
