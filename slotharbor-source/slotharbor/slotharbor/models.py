"""HTTP request shapes. Domain rules remain enforced for non-HTTP callers too."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class Activation(Input):
    active: StrictBool


class NewUser(Input):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "coordinator", "member"] = "member"


class Resource(Input):
    name: str
    code: str
    timezone: str = "Africa/Nairobi"
    capacity: StrictInt = 1
    opens: str = "07:00"
    closes: str = "21:00"
    weekdays: list[StrictInt] = Field(default_factory=lambda: list(range(7)))
    buffer_minutes: StrictInt = 0
    requires_approval: StrictBool = False


class Reservation(Input):
    resource_id: StrictInt
    title: str
    starts: str
    ends: str
    attendees: StrictInt = 1
    count: StrictInt = 1
    interval_days: StrictInt = 7
    key: str
    start_fold: StrictInt | None = None
    end_fold: StrictInt | None = None


class Transition(Input):
    action: Literal["cancel", "approve", "reject"]
    expected_version: StrictInt


class Maintenance(Input):
    resource_id: StrictInt
    starts: str
    ends: str
    reason: str
    start_fold: StrictInt | None = None
    end_fold: StrictInt | None = None
