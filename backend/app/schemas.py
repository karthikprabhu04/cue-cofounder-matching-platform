from typing import Literal

from pydantic import BaseModel, Field


class EmailRequest(BaseModel):
    email: str = Field(min_length=6, max_length=200)


class OtpVerifyRequest(BaseModel):
    email: str = Field(min_length=6, max_length=200)
    code: str = Field(min_length=6, max_length=6)


class ProfileUpsertRequest(BaseModel):
    first_name: str
    last_name: str
    college: str
    course: str
    year: int
    what_have_you_built: str
    skills: list[str]
    commitment_level: Literal["Exploring", "Part-time", "Serious"]
    looking_for: Literal["Technical", "Non-technical", "Either"]
    linkedin_url: str = ""
    cam_email: str = ""


class ConnectRequestCreate(BaseModel):
    recipient_user_id: int
    message: str = Field(min_length=8, max_length=280)


class ConnectRequestRespond(BaseModel):
    status: Literal["accepted", "declined"]
