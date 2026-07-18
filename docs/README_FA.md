<div dir="rtl">

# راهنمای فارسی AI Station

[بازگشت به README اصلی](../README.md)

## معرفی

**AI Station** یک زیرساخت محلی و قابل‌بازتولید برای اجرای مدل‌های هوش
مصنوعی، جست‌وجوی وب، پردازش اسناد، OCR فارسی، RAG و تبدیل گفتار به متن است.

پلتفرم اصلی پروژه:

- Windows 11
- WSL2
- Ubuntu
- Docker Compose
- کارت گرافیک NVIDIA

تمام سرویس‌های اصلی به‌صورت پیش‌فرض فقط روی `127.0.0.1` در دسترس هستند و
برای انتشار مستقیم روی اینترنت طراحی نشده‌اند.

## امکانات اصلی

- رابط Open WebUI
- مدل زبانی محلی مبتنی بر llama.cpp
- API سازگار با OpenAI
- Embedding محلی
- PostgreSQL و pgvector
- Redis
- SearXNG
- Apache Tika
- OCR فارسی و انگلیسی
- Whisper large-v3
- بررسی SHA-256 مدل‌ها
- قفل‌کردن نسخه دقیق Imageهای Docker

## نیازمندی پیشنهادی

| منبع | پیشنهاد |
|---|---|
| حافظه کارت گرافیک | حدود ۲۴ گیگابایت |
| حافظه RAM | ۶۴ گیگابایت |
| فضای خالی | حداقل ۸۰ گیگابایت |
| نوع ذخیره‌سازی | SSD یا NVMe |

## نصب سریع

### دریافت Repository

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
~~~

### بررسی سیستم بدون ایجاد تغییر

~~~bash
./scripts/install.sh --validate-only
~~~

### نصب کامل

~~~bash
sudo ./scripts/install.sh
~~~

بعد از نصب، رابط اصلی از آدرس زیر در دسترس است:

~~~text
http://127.0.0.1:3000
~~~

## نصب مدل‌ها

پروفایل اصلی:

~~~bash
./scripts/provision-models.sh --profile core
~~~

پروفایل کامل شامل مدل برنامه‌نویسی و Reranker:

~~~bash
./scripts/provision-models.sh --profile all
~~~

## دستورات روزمره

~~~bash
make start
make status
make verify
make logs
make stop
make audit
~~~

## مسیرهای اصلی

~~~text
/opt/ai-station          کد، تنظیمات و اسکریپت‌ها
/srv/ai-station          مدل‌ها، کش، داده و نسخه‌های پشتیبان
~~~

## نکات امنیتی

- پورت‌ها به‌صورت پیش‌فرض فقط روی localhost باز می‌شوند.
- فایل `.env` در Git ثبت نمی‌شود.
- مدل‌ها و Backupها خارج از Repository نگهداری می‌شوند.
- نسخه Imageها و مدل‌ها قفل و کنترل می‌شود.
- این سیستم نباید بدون لایه امنیتی مستقل روی اینترنت عمومی منتشر شود.

## مستندات تکمیلی

- [راهنمای نصب](INSTALLATION.md)
- [معماری](ARCHITECTURE.md)
- [عملیات روزمره](OPERATIONS.md)
- [مدیریت مدل‌ها](MODELS.md)
- [رفع خطا](TROUBLESHOOTING.md)

## License

کد و مستندات اختصاصی پروژه تحت License استاندارد MIT منتشر شده‌اند.

مالک Copyright:

**Ramtin Karbaschi — 2026**

مدل‌ها، کتابخانه‌ها و Containerهای شخص ثالث تابع Licenseهای اصلی خود هستند.

</div>
