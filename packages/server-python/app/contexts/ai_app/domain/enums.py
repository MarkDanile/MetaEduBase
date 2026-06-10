from enum import StrEnum


class AiAppStatus(StrEnum):
    DRAFT = "Draft"
    PUBLISHED = "Published"
    DISABLED = "Disabled"
    ARCHIVED = "Archived"


class AiAppVisibility(StrEnum):
    INTERNAL = "internal"
    ROLE_LIMITED = "role_limited"
    PUBLIC = "public"


class AiAppEntryType(StrEnum):
    INTERNAL_ROUTE = "internal_route"
    EXTERNAL_URL = "external_url"
    EMBEDDED = "embedded"
    API = "api"
