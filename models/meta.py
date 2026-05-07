from typing import Optional

from pydantic import BaseModel


class MetaError(BaseModel):
    message: str
    type: str
    code: int
    fbtrace_id: Optional[str] = None