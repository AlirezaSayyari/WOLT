# WOLT — Wake-on-LAN Translator for FortiGate

> MVP version: `0.1.0` · The current release is the tested headless service. The
> management web UI is designed and scheduled for the next implementation phase.

[UX specification](docs/design/01-product-ux.md) ·
[Technical architecture](docs/design/02-architecture-erd.md)

WOLT یک سرویس داخلی و کوچک است که Magic Packet دریافتی از Apache Guacamole را
به فرمان Native Wake-on-LAN در FortiGate تبدیل می‌کند. سرویس برای هر VLAN روی یک
UDP port قراردادی گوش می‌دهد، MAC را از payload استخراج می‌کند و interface و IP
دروازه را از mapping همان port می‌خواند.

## معماری

```text
Guacamole / guacd
  │  UDP unicast magic packet (destination port = mapping ID)
  ▼
WOLT container
  │  validate source + parse MAC + rate limit + map interface
  ▼
FortiGate SSH (direct command in the account's assigned VDOM)
  │  execute wake-on-lan <interface> <mac> 2 9 <gateway_ip>
  ▼
Destination workstation
```

WOLT فقط portهای تعریف‌شده در `config/interfaces.yaml` را bind می‌کند. Port ورودی
صرفاً شناسه mapping است و هیچ‌گاه در فرمان FortiGate استفاده نمی‌شود.

## تنظیم Guacamole

برای نمونه Connection مربوط به VLAN 16:

```text
Wake-on-LAN MAC Address:       02:AA:BB:CC:DD:16
Wake-on-LAN Broadcast Address: 192.0.2.69
Wake-on-LAN UDP Port:          40016
Wake-on-LAN Wait Time:         30
```

Broadcast Address در اینجا IP سرور WOLT است. Source UDP port تصادفی Guacamole
اعتبارسنجی نمی‌شود؛ تنها Source IP باید با `GUACAMOLE_ALLOWED_IP` برابر باشد.

## نصب

```bash
git clone <repository-url>
cd wolt
cp .env.example .env
cp config/interfaces.example.yaml config/interfaces.yaml
mkdir -p ssh
ssh-keyscan -p 22 192.0.2.30 > ssh/known_hosts
chmod 600 .env
chmod 600 ssh/known_hosts
```

مقادیر `.env`، mappingها و host key را متناسب با محیط خود تغییر دهید. فایل‌های
`.env` و `ssh/known_hosts` حاوی اطلاعات حساس‌اند و نباید commit شوند. هر دو فایل
در container به‌صورت read-only mount می‌شوند و container با کاربر غیر root اجرا
می‌شود. Host key ناشناخته یا متفاوت پذیرفته نمی‌شود.

فرمت mapping:

```yaml
listeners:
  "40016":
    interface: "demo-vlan-16"
    gateway_ip: "198.51.100.94"
```

Port باید بین 1024 و 65535 باشد. Mapping خالی، ناقص، تکراری یا دارای interface/IP
نامعتبر مانع startup می‌شود. Credential واقعی را در repository قرار ندهید.

## اجرا و مشاهده

```bash
docker compose up -d --build
docker logs -f wolt
sudo ss -lunp | grep -E '40016|40017|40030'
```

برای capture ترافیک ورودی:

```bash
sudo tcpdump -ni any 'udp portrange 40000-40099' -s0 -vvv -XX
```

## تست

```bash
docker build --target test -t wolt:test .
docker run --rm wolt:test
```

یا در محیط Python 3.12 محلی:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

## دسترسی FortiGate

حساب `wol-service` باید در FortiGate فقط به VDOM کاری خودش و فرمان لازم دسترسی
داشته باشد. WOLT پس از اتصال SSH فقط فرمان `execute wake-on-lan ...` را مستقیماً
با `exec_command` اجرا می‌کند و سپس اتصال را می‌بندد؛ هیچ `config vdom`، `edit`،
`end` یا Interactive Shell اجرا نمی‌شود. Authentication فقط با username/password
تنظیم‌شده انجام می‌شود و agent و کلیدهای تصادفی میزبان غیرفعال‌اند.

## Troubleshooting

- `listener_bind_failed`: port در host استفاده شده یا کاربر اجازه bind ندارد.
- `source_not_allowed`: IP مبدأ با `GUACAMOLE_ALLOWED_IP` یکسان نیست.
- `invalid_magic_packet`: payload دقیقاً 102 بایت نیست، header اشتباه است یا MAC
  شانزده بار یکسان تکرار نشده است. SecureOn 108 بایتی عمداً رد می‌شود.
- `ssh_authentication_failed`: username/password یا دسترسی حساب FortiGate را چک کنید.
- `host_key_verification_failed`: `known_hosts` را با host key صحیح بازسازی کنید؛
  host key جدید به‌طور خودکار پذیرفته نمی‌شود.
- `ssh_timeout`: مسیر شبکه، SSH port و timeoutها را بررسی کنید.
- `command_failed`: نام interface، VDOM، profile حساب و خروجی CLI را بررسی کنید.
- `config_error`: env اجباری یا mapping نامعتبر/خالی است؛ سرویس عمداً start نمی‌شود.
- `wol_request_rate_limited`: همان MAC روی همان listen port در بازه تعیین‌شده قبلاً
  درخواست شده است. مقدار `WOL_RATE_LIMIT_SECONDS` را بررسی کنید.

خطای یک packet یا SSH listener را متوقف نمی‌کند. `SIGTERM` و `SIGINT` socketها را
می‌بندند و threadها را متوقف می‌کنند. Password، payload کامل و environment کامل
هرگز log نمی‌شوند.

## تست واقعی با Guacamole

1. در `config/interfaces.yaml`، UDP port، نام دقیق interface و `gateway_ip` را ثبت کنید.
2. در `.env`، FortiGate، IP واقعی guacd و مسیرها را تنظیم کنید.
3. با `ssh-keyscan` host key را ثبت و با `docker compose up -d --build` اجرا کنید.
4. در Connection مربوطه Guacamole، IP سرور WOLT و UDP port همان mapping را وارد کنید.
5. هم‌زمان `docker logs -f wolt` و در صورت نیاز `tcpdump` بالا را اجرا کنید.
6. Connection را باز کنید و وجود `wol_request_received` و سپس
   `fortigate_wol_success` را در log تأیید کنید.

## License

MIT
