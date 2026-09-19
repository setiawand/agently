from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


@dataclass
class Deps:
    project_id: int
    pipeline_id: int
    mr_iid: int | None = None


class Diagnosis(BaseModel):
    root_cause: str = Field(description="Penjelasan singkat kenapa pipeline gagal")
    confidence: float = Field(ge=0, le=1, description="Confidence 0-1 terhadap diagnosis")
    suggested_action: Literal["rerun", "comment", "escalate"] = Field(
        description="rerun = terlihat flake/infra blip; "
        "comment = masalah nyata di kode, tinggalkan feedback di MR; "
        "escalate = tidak jelas atau berisiko tinggi, butuh manusia"
    )
    comment_text: str = Field(description="Isi komentar yang akan diposting ke MR (atau catatan eskalasi)")
