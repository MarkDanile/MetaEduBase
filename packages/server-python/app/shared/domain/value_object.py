from pydantic import BaseModel


class ValueObject(BaseModel):
    model_config = {"frozen": True, "from_attributes": True}
