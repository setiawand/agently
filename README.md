# Agently

Kumpulan agent operasional ringan berbasis [Pydantic AI](https://ai.pydantic.dev) dan Ollama, untuk kebutuhan internal (CI/CD GitLab dan n8n). Tanpa n8n untuk agent-nya sendiri, tanpa CrewAI/LangChain.

| Agent | Fungsi | Status |
|-------|--------|--------|
| `ci_cd/` | Diagnosis pipeline GitLab yang gagal, lalu komentar otomatis di MR bila yakin | Belum dites ke GitLab asli |
| `n8n/` | Health check workflow, buat workflow baru, perbaiki workflow bermasalah | Health check sudah dites ke n8n asli; create/fix belum |

## Prinsip desain: gate human-in-the-loop ada di kode

Agent **hanya punya tool baca**. Tool tulis (comment MR, rerun job, create/update/activate workflow) tidak didaftarkan ke LLM. Aksi dieksekusi oleh `main.py` berdasarkan output terstruktur agent, lewat gate deterministik. Jadi keamanan tidak bergantung pada kepatuhan model terhadap prompt.

| Aksi | Perlakuan |
|------|-----------|
| Comment di MR | Otomatis, hanya jika `suggested_action == "comment"`, ada `mr_iid`, dan `confidence >= 0.7` |
| Rerun job, escalate | Tidak pernah otomatis. Agent hanya merekomendasikan, manusia yang menjalankan |
| Buat workflow n8n | Otomatis, tetapi workflow dibuat **inactive** (aktivasi manual) |
| Update workflow n8n | Otomatis hanya jika lolos `n8n/guard.py`: tidak menghapus node, tidak mengubah credential, tidak menyentuh trigger. Selain itu `action_taken="escalated"` |
| Aktifkan/nonaktifkan workflow | Tidak tersedia untuk agent |

Log CI juga dibersihkan dari secret sebelum sampai ke LLM, dan data dari GitLab/n8n diperlakukan sebagai data tak tepercaya di system prompt.

## Persyaratan

- Python 3.10+ dan [uv](https://docs.astral.sh/uv/) (atau pip)
- Server Ollama dengan endpoint OpenAI-compatible (`/v1`). Default: `qwen2.5-coder:32b`
- Token GitLab (scope `api`) dan/atau API key n8n

## Instalasi

```bash
git clone git@github.com:setiawand/agently.git
cd agently
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env    # lalu isi nilainya
```

## Konfigurasi (`.env`)

| Variabel | Dipakai oleh | Keterangan |
|----------|--------------|------------|
| `OLLAMA_URL` | semua agent | Harus berakhiran `/v1`. Default `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | semua agent | Default `qwen2.5-coder:32b` |
| `GITLAB_URL`, `GITLAB_TOKEN` | `ci_cd` | URL tanpa trailing slash; token dengan scope `api` |
| `N8N_URL`, `N8N_API_KEY` | `n8n` | API key dari Settings > n8n API |

Semua diambil dari `core/config.py`. Model dibuat lewat `core.model.get_ollama_model()`, jangan menduplikasi setup Ollama di agent.

## Cara pakai

### n8n: health check (tanpa LLM)

Data dikumpulkan dan diklasifikasi oleh kode (paralel), sehingga cepat dan tidak bergantung pada ukuran model.

```bash
python -m n8n.main                      # progress di stderr, JSON di stdout
python -m n8n.main > health.json        # simpan hasilnya saja
```

Setiap workflow diklasifikasi `failing` (eksekusi terakhir error/crashed), `error` (eksekusi gagal dibaca), atau `inactive`. Yang sehat tidak masuk daftar `issues`.

### n8n: penjelasan kegagalan (LLM kecil, tanpa tool)

Kode mengambil workflow `failing` beserta node dan pesan error eksekusi terakhir. LLM hanya menulis penjelasan singkat, tanpa tool dan tanpa JSON terstruktur, jadi cocok untuk model kecil atau kuantisasi agresif.

```bash
OLLAMA_MODEL=qwen3.5:9b python -m n8n.explain
```

```python
from n8n.explain import explain_failures
for f in explain_failures(model_name="qwen3.5:9b"):
    print(f.workflow_name, f.error_node, f.explanation)
```

Kalau LLM gagal, `error_node` dan `error_message` dari kode tetap dikembalikan dan `explanation` berisi catatan kegagalan.

### n8n: buat dan perbaiki workflow (memakai LLM)

```python
from n8n.main import run_create_workflow, run_fix_workflow

r = run_create_workflow("Kirim ringkasan harian ke Telegram jam 8 pagi")
r = run_fix_workflow("ID_WORKFLOW", "node HTTP Request selalu 401")
print(r.model_dump_json(indent=2))
```

Periksa `action_taken` dan `action_detail` di hasilnya: `applied` berarti sudah ditulis ke n8n, `escalated` berarti ditahan untuk review manusia beserta alasannya. Coba dulu di workflow yang tidak penting.

### CI/CD: diagnosis pipeline

```python
from ci_cd.main import diagnose_pipeline

# Tanpa mr_iid: hanya diagnosis, tidak ada yang diposting
d = diagnose_pipeline(project_id=123, pipeline_id=456)

# Dengan mr_iid: auto-comment jika suggested_action == "comment" dan confidence >= 0.7
d = diagnose_pipeline(project_id=123, pipeline_id=456, mr_iid=78)
print(d.model_dump_json(indent=2))
```

Rerun tidak pernah otomatis. Kalau setuju dengan rekomendasinya: `ci_cd.tools.retry_job(project_id, job_id)`.

**Saran bertahap:** jalankan dulu tanpa `mr_iid` dan bandingkan diagnosisnya dengan penyebab sebenarnya di beberapa pipeline lama, baru aktifkan auto-comment.

## Struktur proyek

```
agently/
├── core/            # config (.env), model Ollama, helper HTTP (ApiError)
├── ci_cd/           # agent diagnosis pipeline GitLab
│   ├── schemas.py   # Deps, Diagnosis
│   ├── tools.py     # fungsi GitLab API murni + redaksi secret
│   ├── agent.py     # Agent read-only + tool baca
│   └── main.py      # diagnose_pipeline() + gate
├── n8n/             # agent operasional n8n
│   ├── schemas.py   # Deps, HealthReport, WorkflowProposal, AgentResult
│   ├── tools.py     # fungsi n8n REST API murni
│   ├── health.py    # klasifikasi health check (tanpa LLM)
│   ├── explain.py   # penjelasan kegagalan (LLM tanpa tool, model kecil ok)
│   ├── guard.py     # gate: update workflow aman atau ditahan
│   ├── agent.py     # Agent read-only untuk create/fix
│   └── main.py      # run_health_check/run_create_workflow/run_fix_workflow
└── tests/
```

Pola tiap agent: `schemas.py` (kontrak data) → `tools.py` (fungsi API murni, mudah di-mock) → `agent.py` (definisi Agent + tool baca) → `main.py` (entry point tipis + gate untuk aksi tulis).

## Test

```bash
pytest
```

Test berjalan tanpa jaringan dan tanpa LLM asli (HTTP di-mock, agent memakai `TestModel` dari pydantic-ai), termasuk pengecekan bahwa agent tidak memiliki tool tulis.

## Menambah agent atau tool baru

- Tool baca boleh didaftarkan dengan `@agent.tool` (bungkus dengan `@tool_errors` dari `core.http` agar error HTTP kembali ke LLM sebagai teks).
- Aksi tulis **jangan** didaftarkan ke agent. Buat sebagai fungsi di `tools.py`, panggil dari `main.py` di belakang gate (ambang confidence atau guard deterministik), dan tambahkan test yang membuktikan aksi berisiko tidak berjalan otomatis.

## Pemecahan masalah

| Gejala | Penyebab umum |
|--------|---------------|
| `Base URL belum dikonfigurasi` | `.env` tidak terbaca. Jalankan dari folder proyek |
| `ApiError ... HTTP 401` | Token/API key salah |
| Agent lama atau berputar | Model terlalu kecil untuk tool calling berantai. Coba model lebih besar, atau pindahkan pengumpulan data ke kode seperti health check |
| `Failed to build agently` saat install | Pastikan `[tool.setuptools] packages` ada di `pyproject.toml` (sudah ada di versi terbaru) |
| Banner pydantic-ai mengganggu | `export PYDANTIC_AI_NO_BANNER=1` |

## Belum ada

- Handler webhook (FastAPI) untuk memicu `ci_cd` dari event pipeline GitLab
- Penjadwalan (cron) untuk health check n8n dan notifikasi hasilnya
- Verifikasi endpoint `PUT` update workflow n8n ke instance asli
