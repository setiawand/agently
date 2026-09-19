# Agently

Kumpulan agent operasional ringan berbasis [Pydantic AI](https://ai.pydantic.dev) dan Ollama, untuk kebutuhan internal (CI/CD GitLab dan n8n). Tanpa n8n untuk agent-nya sendiri, tanpa CrewAI/LangChain.

| Agent | Fungsi | Status |
|-------|--------|--------|
| `ci_cd/` | Diagnosis pipeline GitLab yang gagal, lalu komentar otomatis di MR bila yakin | Belum dites ke GitLab asli |
| `tokopedia/` | Cek pesanan toko Tokopedia (pesanan terlambat kirim, permintaan batal pembeli) + ringkasan LLM. **Read-only** | Belum dites ke toko asli |
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
| `AGENTLY_TRACE` | semua agent | `1` = tampilkan aktivitas model langkah demi langkah di stderr (lihat bagian trace) |
| `LLM_THINKING` | semua agent | `off` = matikan mode thinking (kirim `reasoning_effort=none`). Mempercepat model lokal seperti qwen3.5 |
| `LLM_PROVIDER` | semua agent | `ollama` (default) atau `openrouter` |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | jika `openrouter` | Model dalam format OpenRouter, mis. `qwen/qwen-2.5-72b-instruct` |
| `TTS_APP_KEY`, `TTS_APP_SECRET` | `tokopedia` | Dari app di TikTok Shop Partner Center |
| `TTS_SHOP_CIPHER` | `tokopedia` | Opsional; kosong = otomatis jika hanya ada satu toko |
| `TTS_TOKEN_FILE` | `tokopedia` | Lokasi token (default `.tts_tokens.json`, chmod 600, di-gitignore) |
| `TTS_ACCESS_TOKEN`, `TTS_REFRESH_TOKEN` | `tokopedia` | Opsional, hanya untuk bootstrap; biasanya cukup `python -m tokopedia.auth` |
| `GITLAB_URL`, `GITLAB_TOKEN` | `ci_cd` | URL tanpa trailing slash; token dengan scope `api` |
| `N8N_URL`, `N8N_API_KEY` | `n8n` | API key dari Settings > n8n API |

Semua diambil dari `core/config.py`. Model dibuat lewat `core.model.get_model()`, jangan menduplikasi setup model di agent.

### Memakai OpenRouter

```bash
# .env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
```

Atau per panggilan: `get_model("nama/model", provider="openrouter")`; fungsi `summarize_health` dan `explain_failures` menerima `model_name` yang akan dipakai bersama provider dari env.

> **Perhatian data:** dengan OpenRouter, isi prompt (nama workflow, pesan error, log CI) dikirim ke pihak ketiga di luar jaringan kantor. Log CI memang sudah dibersihkan dari secret pola umum, tetapi nama workflow/error tidak difilter. Untuk konteks bank, pastikan kebijakan yang berlaku mengizinkan, atau tetap pakai Ollama on-prem untuk agent CI/CD.

## Melihat aktivitas model (trace lokal)

Tanpa Logfire atau layanan luar. Dengan `AGENTLY_TRACE=1`, setiap langkah tampil langsung di stderr: prompt yang dikirim, proses berpikir model (jika ada), tool call beserta argumen, output tool, jawaban model, jumlah token, dan waktu berjalan.

```bash
AGENTLY_TRACE=1 PYDANTIC_AI_NO_BANNER=1 python -m n8n.explain summary
```

Contoh keluaran:

```
[trace +   0.0s] PROMPT   -> model: <data_health_check> ... 
[trace +   0.0s] menunggu model...
[trace +  12.4s] MODEL    : Ada 2 workflow gagal ...
[trace +  12.4s] usage: in=812 out=96
[trace +  12.4s] selesai. total usage: ...
```

Setiap isi dipotong 400 karakter. Trace memuat isi prompt (nama workflow, error, log), jadi jangan disimpan ke tempat yang dibagi. Untuk dasbor lengkap dengan biaya, pydantic-ai juga mendukung OpenTelemetry ke backend milik sendiri.

## Cara pakai

### n8n: health check (tanpa LLM)

Data dikumpulkan dan diklasifikasi oleh kode (paralel), sehingga cepat dan tidak bergantung pada ukuran model.

```bash
python -m n8n.main                      # progress di stderr, JSON di stdout
python -m n8n.main > health.json        # simpan hasilnya saja
```

Setiap workflow diklasifikasi `failing` (eksekusi terakhir error/crashed), `error` (eksekusi gagal dibaca), atau `inactive`. Yang sehat tidak masuk daftar `issues`.

### n8n: ringkasan health check (LLM kecil, tanpa tool)

Ringkasan singkat siap kirim (Telegram/Slack). Inputnya sudah dipadatkan oleh kode; kalau LLM gagal, hasilnya jatuh ke ringkasan deterministik.

```bash
OLLAMA_MODEL=qwen3.5:9b python -m n8n.explain summary
```

```python
from n8n.explain import summarize_health
print(summarize_health(model_name="qwen3.5:9b"))
```

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

### Tokopedia: cek pesanan (read-only)

Tokopedia kini memakai API TikTok Shop Partner Center. Agent ini untuk **penjual dengan toko sendiri** (jenis app: *Custom app*). Yang dilakukan hanya membaca; tidak ada aksi kirim, batalkan, atau balas pembeli. Semua itu tetap manual.

**Setup satu kali** (mengikuti dokumentasi resmi, [partner.tiktokshop.com](https://partner.tiktokshop.com)):

1. Daftar sebagai developer di Partner Center, buat **Custom app**, aktifkan scope `seller.order.info` dan `seller.authorization.info`.
2. Isi `TTS_APP_KEY` dan `TTS_APP_SECRET` di `.env`.
3. Bagikan *authorization link* app ke akun seller Anda sendiri, setujui, lalu ambil `auth_code` dari redirect URL.
4. Tukar dengan token (disimpan otomatis; access token 7 hari akan di-refresh sendiri, refresh token berputar sehingga wajib disimpan):

```bash
python -m tokopedia.auth <auth_code>
```

**Pemakaian:**

```bash
python -m tokopedia.main            # JSON laporan (tanpa LLM)
python -m tokopedia.main summary    # ringkasan singkat via LLM (tanpa tool)
```

```python
from tokopedia.main import run_order_check, summarize_orders
r = run_order_check(days=7, overdue_hours=24)
for i in r.issues:
    print(i.kind, i.order_id, i.detail)
```

Yang ditandai: pesanan `AWAITING_SHIPMENT` lebih lama dari `overdue_hours` sejak dibuat (default 24 jam), dan pesanan dengan permintaan batal dari pembeli yang belum ditutup. Data pembeli (nama, alamat, telepon, email) dibuang di kode dan tidak pernah dikirim ke LLM. Kalau LLM gagal, hasil jatuh ke ringkasan dari kode. Error API dicek dari `code` di body respons (TikTok membalas HTTP 200 walau gagal).

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
├── core/            # config (.env), model (Ollama/OpenRouter), helper HTTP (ApiError), trace lokal
├── ci_cd/           # agent diagnosis pipeline GitLab
│   ├── schemas.py   # Deps, Diagnosis
│   ├── tools.py     # fungsi GitLab API murni + redaksi secret
│   ├── agent.py     # Agent read-only + tool baca
│   └── main.py      # diagnose_pipeline() + gate
├── tokopedia/       # agent pesanan Tokopedia (TikTok Shop API), read-only
│   ├── auth.py      # token: tukar auth_code, refresh otomatis, simpan aman
│   ├── tools.py     # tanda tangan HMAC-SHA256 + pencarian pesanan (tanpa PII)
│   ├── report.py    # klasifikasi pesanan bermasalah (tanpa LLM)
│   ├── schemas.py   # OrderIssue, OrderReport
│   └── main.py      # run_order_check(), summarize_orders()
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
| Tokopedia: `code=...` dengan HTTP 200 | Error dari TikTok Shop (token kedaluwarsa, scope kurang, signature salah). Cek pesan di `ApiError` dan scope app di Partner Center |
| Tokopedia: `Ditemukan N toko; isi TTS_SHOP_CIPHER` | Akun punya lebih dari satu toko; salin cipher toko yang dipakai ke `.env` |
| Agent lama atau berputar | Model terlalu kecil untuk tool calling berantai. Coba model lebih besar, atau pindahkan pengumpulan data ke kode seperti health check |
| `Failed to build agently` saat install | Pastikan `[tool.setuptools] packages` ada di `pyproject.toml` (sudah ada di versi terbaru) |
| Model lokal lambat di `menunggu model...` | Lihat trace: banyak `THINKING` atau `out=` besar berarti model terlalu banyak berpikir, coba `LLM_THINKING=off`. Cek juga `ollama ps` (kolom PROCESSOR: kalau ada CPU, model tidak muat penuh di GPU/RAM) |
| Banner pydantic-ai mengganggu | `export PYDANTIC_AI_NO_BANNER=1` |

## Belum ada

- Tokopedia: verifikasi ke toko asli (khususnya nama field respons pesanan dan `/api/v2/token/get`), webhook pesanan, dan aksi tulis (sengaja belum ada)
- Handler webhook (FastAPI) untuk memicu `ci_cd` dari event pipeline GitLab
- Penjadwalan (cron) untuk health check n8n dan notifikasi hasilnya
- Verifikasi endpoint `PUT` update workflow n8n ke instance asli
