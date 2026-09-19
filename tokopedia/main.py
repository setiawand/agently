"""Entry point Tokopedia (read-only). Tidak ada aksi tulis: kirim/batal/balas pembeli dilakukan manusia."""

import sys

from pydantic_ai import Agent

from core.http import ApiError
from core.model import get_model
from core.trace import run_agent
from tokopedia import report, tools
from tokopedia.schemas import OrderReport

summarizer = Agent(
    None,
    system_prompt=(
        "Kamu menulis ringkasan operasional toko Tokopedia untuk penjual, bahasa Indonesia, maksimal 5 baris, "
        "cocok untuk pesan Telegram/Slack. Utamakan permintaan batal dan pesanan terlambat kirim, sebut ID dan jumlah. "
        "Hanya pakai data yang diberikan; jangan mengarang."
    ),
)


def run_order_check(days: int = 7, overdue_hours: float = 24, progress=None) -> OrderReport:
    """Deterministik dan read-only; tanpa LLM."""
    return report.build_order_report(tools.fetch_order_snapshot(days, progress), overdue_hours)


def summarize_orders(days: int = 7, overdue_hours: float = 24, model_name: str | None = None, progress=None) -> str:
    """Ringkasan LLM (tanpa tool, cocok untuk model kecil); jatuh ke ringkasan kode jika LLM gagal."""
    r = run_order_check(days, overdue_hours, progress)
    lines = [r.summary, "Status: " + ", ".join(f"{k}={v}" for k, v in sorted(r.status_counts.items()))]
    lines += [f"- [{i.kind}] {i.order_id} ({i.age_hours:g} jam): {i.detail}" for i in r.issues[:20]]
    if len(r.issues) > 20:
        lines.append(f"- ... dan {len(r.issues) - 20} lainnya")
    try:
        prompt = "<data_toko>\n" + "\n".join(lines) + "\n</data_toko>"
        return run_agent(summarizer, prompt, model=get_model(model_name)).output.strip()
    except Exception as e:  # jangan sampai notifikasi mati karena model bermasalah
        return f"{r.summary} (ringkasan LLM gagal: {type(e).__name__})"


if __name__ == "__main__":
    def _p(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    try:
        if sys.argv[1:] == ["summary"]:
            print(summarize_orders(progress=_p))
        else:
            print(run_order_check(progress=_p).model_dump_json(indent=2))
    except ApiError as e:
        sys.exit(f"ERROR: {e}")
