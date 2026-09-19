"""Entry point tipis -- panggil dari webhook GitLab (event pipeline, status=failed) atau CLI."""

from core.model import get_model
from core.trace import run_agent
from ci_cd.agent import agent
from ci_cd.schemas import Deps, Diagnosis
from ci_cd import tools

AUTO_COMMENT_MIN_CONFIDENCE = 0.7


def diagnose_pipeline(project_id: int, pipeline_id: int, mr_iid: int | None = None) -> Diagnosis:
    deps = Deps(project_id=project_id, pipeline_id=pipeline_id, mr_iid=mr_iid)
    result = run_agent(
        agent,
        f"A GitLab pipeline just failed. project_id={project_id}, "
        f"pipeline_id={pipeline_id}. Diagnose it.",
        deps=deps,
        model=get_model(),
    )
    diagnosis = result.output

    # Human-in-the-loop gate: hanya auto-act untuk aksi low-risk dan confidence memadai.
    if (
        diagnosis.suggested_action == "comment"
        and mr_iid
        and diagnosis.confidence >= AUTO_COMMENT_MIN_CONFIDENCE
    ):
        tools.post_mr_comment(project_id, mr_iid, diagnosis.comment_text)
    # 'rerun' dan 'escalate' sengaja tidak auto-apply -- konfirmasi manual dulu
    # sampai diagnosisnya terbukti bisa dipercaya.

    return diagnosis


if __name__ == "__main__":
    d = diagnose_pipeline(project_id=123, pipeline_id=456, mr_iid=78)
    print(d.model_dump_json(indent=2))
