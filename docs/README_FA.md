<div dir="rtl">

# راهنمای فارسی AI Station

[بازگشت به README اصلی](../README.md)

## معرفی

**AI Station** یک ایستگاه کاری محلی و قابل‌بازتولید برای گفت‌وگوی خصوصی با
مدل‌ها، RAG، پردازش اسناد، OCR فارسی، جست‌وجوی وب و تبدیل گفتار به متن است —
بدون ارسال پرامپت به API ابری.

پلتفرم اصلی:

- Windows 11 + WSL2 + Ubuntu
- Docker Compose
- کارت گرافیک NVIDIA

سرویس‌ها به‌صورت پیش‌فرض فقط روی `127.0.0.1` در دسترس‌اند.

## امکانات اصلی

- رابط Open WebUI روی `:3000`
- API چندپروژه‌ای LiteLLM روی `:4000` (سازگار با OpenAI)
- موتور پیش‌فرض llama.cpp با پروفایل‌های general / coder / reasoning / vision
- Embedding محلی + PostgreSQL/pgvector
- Apache Tika + OCR فارسی/انگلیسی
- SearXNG و Whisper large-v3 محلی
- قفل digest برای Imageها و SHA-256 برای مدل‌ها
- کنترل پذیرش منابع (`ai provider`) برای یک مدل سنگین در هر لحظه

## نیازمندی پیشنهادی

| منبع | پیشنهاد |
|---|---|
| VRAM | حدود ۲۴ گیگابایت |
| RAM | ۶۴ گیگابایت |
| فضای خالی | حداقل ۸۰ گیگابایت |
| ذخیره‌سازی | SSD / NVMe |

## نصب سریع

دستورهای آماده (بعد از نصب NVIDIA / WSL یا Docker):

**ویندوز (PowerShell):**

~~~powershell
irm https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/windows/Install-AIStation.ps1 | iex
~~~

**لینوکس:**

~~~bash
curl -fsSL https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/linux/install-ai-station.sh | bash
~~~

یا بستهٔ zip را از
[Releases](https://github.com/Ramtin-Karbaschi/ai-station/releases/latest)
دانلود کنید.

### کلون کامل ریپازیتوری

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
~~~

سپس:

~~~text
http://127.0.0.1:3000
~~~

برای اپلیکیشن‌ها:

~~~text
http://127.0.0.1:4000/v1
~~~

## مدل‌ها

~~~bash
./scripts/provision-models.sh --profile core
./scripts/provision-models.sh --profile all
ai models use general
~~~

## دستورات روزمره

~~~bash
make start
make status
make verify
make stop
make audit
ai provider start llama-cpp-general --dry-run
~~~

## مسیرها

~~~text
/opt/ai-station          کد و تنظیمات
/srv/ai-station          مدل‌ها، کش، بکاپ و runtime
~~~

## امنیت

- پورت‌ها پیش‌فرض فقط localhost
- فایل `.env` واقعی در Git نیست
- مدل‌ها و Imageها پین و قابل‌تأییدند
- انتشار مستقیم روی اینترنت عمومی پشتیبانی نمی‌شود

## مستندات

- [نصب](INSTALLATION.md)
- [معماری](ARCHITECTURE.md)
- [پلتفرم](PLATFORM.md)
- [عملیات](OPERATIONS.md)
- [مدل‌ها](MODELS.md)
- [وضعیت جاری](ops/AI_STATION_CURRENT_STATE.md)

## License

MIT — Copyright © 2026 **Ramtin Karbaschi**

</div>
