import json
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, Any, Dict, List

class TaskDifficulty(Enum):
    SIMPLE = "Simple"
    MEDIUM = "Medium"
    HARD = "Hard"

@dataclass
class OptimizeTask:
    task_id: int
    difficulty: TaskDifficulty
    nl_question: str
    db_name: str
    original_sql: str
    original_scanned_rows: int
    optimized_sql: Optional[str] = None
    optimized_scanned_rows: Optional[int] = None
    optimization_type: Optional[List[str]] = None

    @staticmethod
    def _clean_sql(sql_content: str) -> Optional[str]:
        return sql_content.replace('\\n', '').replace("\\'", "'")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['difficulty'] = self.difficulty.value
        return data
    
    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=4)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizeTask':
        data['difficulty'] = TaskDifficulty(data['difficulty'])
        data['original_sql'] = cls._clean_sql(data['original_sql'])
        data['optimized_sql'] = cls._clean_sql(data['optimized_sql'])
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'OptimizeTask':
        data = json.loads(json_str)
        return cls.from_dict(data)