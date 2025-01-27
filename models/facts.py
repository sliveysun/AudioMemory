from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field

from database._client import document_id_from_seed
from models.memory import CategoryEnum


class FactCategory(str, Enum):
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    other = "other"


class Fact(BaseModel):
    content: str = Field(description="The content of the fact")
    category: FactCategory = Field(description="The category of the fact", default=FactCategory.other)

    class Config:
        arbitrary_types_allowed = True  # 允许任意类型
        # 使用 json_encoders 将 datetime 转换为字符串
        json_encoders = {
            datetime: lambda v: v.isoformat()  # 可以用其他格式
        }

    def dict(self):
        data = self.model_dump(mode="json")
        #del data['started_at']
        return data

    @staticmethod
    def get_facts_as_str(facts: List):
        result = ''
        for f in facts:
            result += f"- {f.content} ({f.category.value})\n"
        return result

class Facts(BaseModel):
    facts: List[Fact] = Field(
        min_items=0,
        max_items=3,
        description="List of new user facts, preferences, interests, or topics.",
    )

class FactDB(Fact):
    id: str
    uid: str
    created_at: datetime
    updated_at: datetime

    # if manually added
    memory_id: Optional[str] = None
    memory_category: Optional[CategoryEnum] = None

    reviewed: bool = False
    user_review: Optional[bool] = None

    manually_added: bool = False
    edited: bool = False
    deleted: bool = False

    class Config:
        arbitrary_types_allowed = True  # 允许任意类型
        # 使用 json_encoders 将 datetime 转换为字符串
        json_encoders = {
            datetime: lambda v: v.isoformat()  # 可以用其他格式
        }

    def dict(self):
        data = self.model_dump(mode="json")
        data['user_id'] = data['uid']
        del data['uid']
        #del data['started_at']
        return data

    @staticmethod
    def from_fact(fact: Fact, uid: str, memory_id: str, memory_category: CategoryEnum) -> 'FactDB':
        return FactDB(
            id=document_id_from_seed(fact.content),
            uid=uid,
            content=fact.content,
            category=fact.category,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            memory_id=memory_id,
            memory_category=memory_category,
        )
