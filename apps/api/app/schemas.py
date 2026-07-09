from pydantic import BaseModel


class ReferencePhotoOut(BaseModel):
    id: str
    title: str
    collection: str | None
    thumbnail_url: str

    model_config = {"from_attributes": True}


class JobCreateOut(BaseModel):
    job_id: str


class JobStatusOut(BaseModel):
    status: str
    result_urls: list[str] | None
    error: str | None

    model_config = {"from_attributes": True}


class JobDebugOut(BaseModel):
    prompt_used: str | None
    attempts: int