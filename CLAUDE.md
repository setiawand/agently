# Agently — konteks proyek

Kumpulan agent operasional yang dipakai internal (J Trust Bank IT + side project),
semuanya lightweight — tidak pakai n8n untuk agent-nya sendiri, tidak pakai CrewAI.

## Kenapa Pydantic AI

Sudah dicoba CrewAI, dirasa terlalu berat (banyak dependency, telemetry, abstraksi
yang tidak perlu untuk kasus single-agent tool-calling). Pydantic AI dipilih karena:
- Tool = fungsi Python biasa, tidak ada DSL
- Output terstruktur pakai Pydantic model langsung (validasi + retry otomatis)
- Model-agnostic, jalan native ke Ollama via endpoint OpenAI-compatible
- Footprint kecil dibanding LangChain/CrewAI

## Model

Semua agent pakai Ollama yang jalan di server RTX 4090 kantor (4x GPU),
model default `qwen2.5-coder:32b`. Konfigurasi di `core/config.py` dan
`core/model.py` — jangan duplikasi setup Ollama di tiap agent, selalu
import dari `core.model.get_model()` (provider via `LLM_PROVIDER`: ollama default, atau openrouter -- cloud, data keluar jaringan).

## Prinsip desain: human-in-the-loop gate

Aksi low-risk (comment di MR, fix field kosong di workflow) boleh auto-apply.
Aksi berisiko (rerun job, escalate, ubah credential, hapus node, ubah trigger
produksi) TIDAK auto-apply — agent hanya mendiagnosis dan menjelaskan,
manusia yang konfirmasi manual. Ini penting khususnya untuk agent CI/CD karena
konteksnya bank (J Trust Bank), bukan side project bebas risiko.

Kalau menambah agent baru atau tool baru, pertahankan pola ini: pisahkan
"agent boleh langsung eksekusi" vs "agent hanya rekomendasi, tunggu approve".

## Struktur folder

```
agently/
├── core/           # config (.env), model Ollama, helper HTTP (ApiError), dipakai semua agent
├── ci_cd/          # agent diagnosis pipeline GitLab yang gagal
│   ├── schemas.py  # Deps, Diagnosis
│   ├── tools.py    # fungsi GitLab API murni, testable tanpa LLM (+ redaksi secret di log)
│   ├── agent.py    # definisi Agent + @agent.tool wrapper
│   └── main.py     # entry point: diagnose_pipeline()
├── n8n/            # agent cek kesehatan / buat / perbaiki workflow n8n
│   ├── schemas.py  # Deps, HealthReport, AgentResult
│   ├── tools.py    # fungsi n8n REST API murni, testable tanpa LLM
│   ├── guard.py    # gate deterministik: update workflow aman auto-apply atau ditahan
│   ├── agent.py    # definisi Agent + @agent.tool wrapper
│   └── main.py     # entry point: run_health_check(), run_create_workflow(), run_fix_workflow()
└── tests/
```

Pola tiap agent baru: `schemas.py` (kontrak data) → `tools.py` (fungsi API murni,
gampang di-mock untuk test) → `agent.py` (definisi Agent + tool registration) →
`main.py` (entry point tipis, dipanggil dari webhook/cron/CLI).

## Gate human-in-the-loop ditegakkan di kode, bukan di prompt

Agent HANYA punya tool baca. Tool tulis (comment MR, rerun job, create/update/activate
workflow n8n) tidak didaftarkan ke LLM; dieksekusi `main.py` berdasarkan output
terstruktur (`Diagnosis` / `AgentResult.proposal`):
- ci_cd: auto-comment hanya jika `suggested_action == "comment"` dan confidence >= 0.7;
  rerun/escalate tidak pernah auto-apply.
- n8n: workflow baru dibuat (inactive); update hanya auto-apply jika lolos `n8n/guard.py`
  (tidak hapus node, tidak ubah credential/trigger), selain itu `action_taken="escalated"`.
Jangan daftarkan tool tulis ke `@agent.tool`.

## Status saat ini

- `ci_cd/`, `n8n/`: belum dites ke GitLab / n8n asli. Endpoint PUT update workflow n8n perlu diverifikasi.
- Belum ada webhook handler (FastAPI/Flask); masih dipanggil manual/CLI
- `tests/`: unit test tanpa jaringan/LLM (`pytest`, pakai `TestModel` dari pydantic-ai)

## Env vars yang dibutuhkan

Lihat `.env.example`. Ringkasnya: `OLLAMA_URL`, `OLLAMA_MODEL` (shared),
`GITLAB_URL` + `GITLAB_TOKEN` (ci_cd), `N8N_URL` + `N8N_API_KEY` (n8n).

## Aturan kerja

Setiap perubahan kode/perilaku/konfigurasi langsung disertai update `README.md` (dan `.env.example`
bila ada env var baru) dalam commit yang sama. Jangan menunda dokumentasi ke akhir.
