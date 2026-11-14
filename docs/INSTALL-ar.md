<div dir="rtl">

# تثبيت Technting CMS

يشرح هذا الدليل الطريق من خادم فارغ إلى موقع منشور. النسخة الإنجليزية: [INSTALL.md](INSTALL.md).

يتكوّن Technting CMS من جزأين:

- **لوحة التحكم**: تطبيق Django يعمل عبر gunicorn، ويعمل فيه المحررون، وتكون عادةً على عنوان مثل `cms.example.com`.
- **الموقع العام**: ملفات ثابتة تكتبها لوحة التحكم في مجلد، ويقدّمها nginx أو أي خادم ويب آخر على عنوانكم الرئيسي مثل `example.com`.

يرسل نموذج التواصل ونماذج Technting Forms وعدّاد الزيارات والنشرة البريدية طلباتها من الموقع العام إلى لوحة التحكم
(`/api/` و`/f/` و`/newsletter/`)، لذلك يحوّل خادم الموقع العام هذه المسارات إلى لوحة التحكم.

## المتطلبات

| | Docker | برنامج التثبيت على Linux | التثبيت اليدوي |
|---|---|---|---|
| النظام | أي خادم فيه Docker مع إضافة compose | ‏Ubuntu 24.04 أو أحدث، أو Debian مع Python 3.12 أو أحدث | أي نظام فيه Python 3.12 أو أحدث |
| الذاكرة | تكفي 512 ميغابايت لموقع صغير | مثل ذلك | مثل ذلك |
| قاعدة البيانات | ‏SQLite، ولا تحتاج إلى إعداد؛ أو MySQL أو MariaDB أو PostgreSQL ([قاعدة البيانات](#قاعدة-البيانات)) | مثل ذلك | مثل ذلك |

احصلوا على الشيفرة إما من ملف إصدار (`technting-cms-<version>.tar.gz` أو `.zip`، وتحققوا منه بملف `SHA256SUMS`) وإما من نسخة Git.

## قاعدة البيانات

‏SQLite هي الخيار الافتراضي: ملف واحد داخل مجلد البيانات، بلا تثبيت ولا إعداد، وهي الأنسب للمواقع الصغيرة والمتوسطة التي
يعمل عليها عدد قليل من المحررين. أما MySQL أو MariaDB أو PostgreSQL فاختاروها للمواقع الأكبر، أو حين يعمل كثيرون على
المحتوى في الوقت نفسه، أو حين يوفّر لكم مزوّد الاستضافة خادم قاعدة بيانات (استضافة مشتركة أو قاعدة بيانات مُدارة).

| `TECHNTING_CMS_DB_ENGINE` | قاعدة البيانات | المشغّل |
|---|---|---|
| `sqlite` (الافتراضي) | ‏SQLite 3 | مدمج في Python |
| `mysql` (أو `mariadb`) | ‏MySQL 8.0 أو أحدث، أو MariaDB 10.6 أو أحدث | `requirements-mysql.txt` (‏mysqlclient) |
| `postgresql` | ‏PostgreSQL 14 أو أحدث | `requirements-postgresql.txt` (‏psycopg) |

مع `mysql` و`postgresql` اضبطوا بيانات الاتصال في `.env` (أو في بيئة الخادم):

<div dir="ltr">

```
TECHNTING_CMS_DB_ENGINE=mysql
TECHNTING_CMS_DB_NAME=technting_cms
TECHNTING_CMS_DB_USER=technting_cms
TECHNTING_CMS_DB_PASSWORD=<the password you chose>
TECHNTING_CMS_DB_HOST=127.0.0.1      # default
TECHNTING_CMS_DB_PORT=3306           # default: 3306 for mysql, 5432 for postgresql
```

</div>

ترفض لوحة التحكم أن تبدأ إذا كان نوع قاعدة البيانات غير معروف أو كان الاسم أو المستخدم أو كلمة المرور ناقصاً. ولا تُكتب
بيانات الاتصال في معالج الإعداد أبداً، لكن ملخّص المعالج وصفحة الإعدادات ثم التحديثات يعرضان قاعدة البيانات المستخدمة.
تجنّبوا في كلمة المرور المسافات وعلامات الاقتباس والشرطة المائلة العكسية والرمزين `$` و`#`، لأن قيم `.env` تُقرأ من دون علامات اقتباس.

أنشئوا قاعدة البيانات ومستخدمها بأنفسكم قبل التشغيل الأول، فلا ينشئ Technting CMS ولا `install.sh` أي مستخدم أو كلمة
مرور لقاعدة البيانات. في MySQL وMariaDB استخدموا دائماً `utf8mb4` لتُحفظ النصوص العربية والرموز التعبيرية كما هي:

<div dir="ltr">

```sql
CREATE DATABASE technting_cms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'technting_cms'@'localhost' IDENTIFIED BY '<a long random password>';
GRANT ALL PRIVILEGES ON technting_cms.* TO 'technting_cms'@'localhost';
```

</div>

إذا كانت قاعدة البيانات على جهاز آخر فضعوا مكان `localhost` عنوان الجهاز الذي يتصل منه Technting CMS، وللاتصال عبر
المقبس المحلي اضبطوا `TECHNTING_CMS_DB_HOST=localhost`. وفي PostgreSQL:

<div dir="ltr">

```sql
CREATE USER technting_cms WITH PASSWORD '<a long random password>';
CREATE DATABASE technting_cms OWNER technting_cms ENCODING 'UTF8' TEMPLATE template0;
```

</div>

بعد ذلك ثبّتوا المشغّل وشغّلوا الترحيلات: يتولى `install.sh --db mysql` (أو `--db postgresql`) الأمرين ويكتب الإعدادات في
`.env`، أما يدوياً فنفّذوا `.venv/bin/pip install -r requirements-mysql.txt` ثم `manage.py migrate`. وفي Debian وUbuntu يُبنى
مشغّل MySQL من الشيفرة المصدرية، فثبّتوا أولاً `pkg-config default-libmysqlclient-dev build-essential python3-dev`. وتحتاج
النسخ الاحتياطية إلى أدوات العميل أيضاً: `mariadb-client` (أو عميل MySQL) مع MySQL وMariaDB، و`postgresql-client` مع
PostgreSQL، بإصدار رئيسي مساوٍ لإصدار الخادم أو أحدث منه.

في Docker: تحتوي الصورة على المشغّلين وأدوات العميل، فلا تحتاجون إلا إلى الإعدادات. ولتشغيل MariaDB في حاوية خاصة بجوار
Technting CMS، ضعوا `TECHNTING_CMS_DB_PASSWORD` و`MARIADB_ROOT_PASSWORD` في `.env`، ثم أضيفوا الملف الإضافي:

```bash
docker compose -f docker-compose.yml -f deploy/docker/docker-compose.mysql.yml up -d --build
```

تنشئ الخدمة `db` (‏`mariadb:11`) قاعدة البيانات ومستخدمها من هاتين القيمتين عند تشغيلها الأول، وتحفظ بياناتها في وحدة
التخزين `mariadb`، ولا تنشر أي منفذ، ولا تبدأ `app` و`scheduler` إلا بعد أن تصبح سليمة. استخدموا الخيارين `-f` نفسيهما في
كل أمر `docker compose` لاحق. وإذا كان خادم قاعدة البيانات خارج Docker، فاضبطوا قيم `TECHNTING_CMS_DB_*` في `.env` بدلاً
من ذلك وشغّلوا المجموعة كالمعتاد. ويسأل الأمر `bash install.sh --docker --db mysql` عن كلمتي المرور، ويكتبهما في `.env`،
ويستخدم الملف الإضافي.

لنقل موقع قائم من SQLite إلى قاعدة بيانات أخرى: نفّذوا بالإعدادات القديمة
`manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission > content.json`، ثم بالإعدادات
الجديدة `migrate` و`loaddata content.json`. ولا تُسترجع النسخة الاحتياطية إلا إلى نوع قاعدة البيانات الذي أُخذت منه. ولا
يعمل `demo_reset` (النسخة التجريبية العامة) إلا مع SQLite.

## الطريقة الأولى: Docker

```bash
tar xzf technting-cms-0.4.0.tar.gz && cd technting-cms-0.4.0
bash install.sh --docker
```

يتحقق الأمر `install.sh --docker` من وجود Docker، ثم يكتب ملف `.env` إن لم يكن موجوداً (مفتاح سري جديد ومفتاح إعداد وأسماء
المضيفين المسموح بها)، ثم يشغّل `docker compose up -d --build`، ويطبع في النهاية عنوان معالج الإعداد، مثل
`http://localhost:8000/setup/?token=...`. ويمكنكم تشغيل `docker compose up -d --build` بأنفسكم أيضاً، وعندها يُولَّد مفتاح سري ومفتاح إعداد
عند التشغيل الأول ويُحفظان في وحدة التخزين (`/data/var/secret_key` و`/data/var/setup_token`)، ويظهر عنوان المعالج مع المفتاح في `docker compose logs app`.

الخدمات التي تعمل:

| الخدمة | عملها | المنفذ |
|---|---|---|
| `app` | لوحة التحكم (gunicorn)، وتشغّل ترحيلات قاعدة البيانات عند بدئها | داخل المجموعة فقط |
| `scheduler` | ينفّذ `publish_due` كل خمس دقائق (الصفحات المجدولة والمهام الدورية)، و`backup --keep 14` مرة يومياً بعد الساعة 02:00 | لا يوجد |
| `web` | ‏nginx: يقدّم الموقع المنشور، ولوحة التحكم مع ملفاتها الثابتة | 8080 للموقع، و8000 للوحة التحكم |

وحدات التخزين: `data` (قاعدة البيانات والملفات المرفوعة والذاكرة المؤقتة والنسخ الاحتياطية و`site.env`)، و`site` (الموقع المنشور).
احتفظوا بنسخة من وحدة `data`، أو انسخوا اللقطات من `/data/backups`.

قيم مفيدة في `.env` مع Docker: `TECHNTING_CMS_ALLOWED_HOSTS` (أضيفوا اسمي مضيف لوحة التحكم والموقع)، و`TECHNTING_CMS_DASHBOARD_PORT`
و`TECHNTING_CMS_SITE_PORT` (المنافذ المنشورة)، و`TECHNTING_CMS_SCHEDULE_SECONDS` و`TECHNTING_CMS_BACKUP_HOUR`
و`TECHNTING_CMS_BACKUP_KEEP`، و`GUNICORN_CMD_ARGS` (عدد العمليات والخيوط). لا تضعوا `TECHNTING_CMS_SITE_NAME` ولا `_SITE_URL`
ولا `_THEME` في الملف، فمعالج الإعداد يضبطها، وأي قيمة لها في `.env` تظهر في المعالج للقراءة فقط.

على خادم عام، ضعوا وكيلاً يقدّم TLS أمام المنفذين. مثال مع Caddy:

<div dir="ltr">

```
cms.example.com {
  reverse_proxy 127.0.0.1:8000
}
example.com {
  reverse_proxy 127.0.0.1:8080
}
```

</div>

لتشغيل أوامر داخل المجموعة استخدموا `docker compose exec app python manage.py <command>`، مثل `changepassword <username>`.
وللسجلات: `docker compose logs -f app scheduler web`.

## الطريقة الثانية: برنامج التثبيت على Linux

```bash
tar xzf technting-cms-0.4.0.tar.gz && cd technting-cms-0.4.0
sudo bash install.sh --nginx --dashboard-host cms.example.com --site-host example.com
```

خطوات البرنامج بالترتيب، ويتخطى كل خطوة أُنجزت من قبل:

1. يثبّت الحزم الناقصة (`python3-venv` و`git`، و`nginx` مع الخيار `--nginx`، وحزم بناء مشغّل قاعدة البيانات وأدوات
   عميلها مع `--db mysql` أو `--db postgresql`)، ويتحقق من وجود Python 3.12 أو أحدث.
2. ينشئ مستخدم النظام `technting` والمجلدات المذكورة أدناه.
3. ينسخ الشيفرة إلى `/home/technting/technting-cms`، ويسأل أولاً إذا وجد شيفرة سابقة.
4. ينشئ البيئة الافتراضية ويثبّت `requirements.txt` (ومعه `requirements-mysql.txt` أو `requirements-postgresql.txt` مع الخيار `--db`).
5. يكتب ملف `.env` (بالصلاحيات 600) مع مفتاح سري جديد ومفتاح إعداد، ومع الخيار `--db` بيانات الاتصال بقاعدة البيانات التي
   قرأها من `TECHNTING_CMS_DB_*` أو سأل عنها (وتُكتب كلمة المرور من دون أن تظهر على الشاشة)، إلا إذا كان الملف موجوداً.
6. يشغّل `migrate` و`collectstatic`.
7. يثبّت `technting-cms.service` ومؤقتَي النشر المجدول والنسخ الاحتياطي من مجلد `deploy/` بالمستخدم والمجلدات والمنفذ الذي
   اخترتموه، ويسأل قبل استبدال أي ملف وحدة عدّلتموه، ثم يفعّلها ويشغّلها.
8. مع الخيار `--nginx`: يكتب `/etc/nginx/sites-available/technting-cms.conf` (‏http عادي للعنوانين) ومراقب ملف التحويلات.
9. يطبع عنوان معالج الإعداد.

الخيارات: `--user` و`--dir` و`--var-dir` و`--output-dir` و`--dashboard-host` و`--site-host` و`--port` و`--db` و`--yes`
(راجعوا `bash install.sh --help`). من دون `--nginx` تستمع لوحة التحكم على `127.0.0.1:18150` فقط، فاستخدموا
`deploy/cms.example.com.conf` نقطة بداية لإعداد nginx الخاص بكم، أو افتحوا المعالج عبر نفق SSH
(`ssh -L 18150:127.0.0.1:18150 you@server` ثم `http://localhost:18150/setup/`).

فعّلوا TLS قبل مشاركة العنوان، مثلاً: `sudo certbot --nginx -d cms.example.com -d example.com`. وإلى أن يعمل TLS، يحتاج
تسجيل الدخول عبر http عادي إلى اسم مضيف أن تضعوا `TECHNTING_CMS_HTTPS=0` في `.env` ثم تنفّذوا `sudo systemctl restart technting-cms`،
وأعيدوا القيمة إلى 1 بعد تفعيل TLS.

## الطريقة الثالثة: التثبيت اليدوي

1. ‏`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (وأضيفوا `-r requirements-mysql.txt` أو
   `-r requirements-postgresql.txt` لقاعدة بيانات أخرى، راجعوا [قاعدة البيانات](#قاعدة-البيانات))
2. ‏`cp .env.example .env`، ثم اضبطوا على الأقل `TECHNTING_CMS_SECRET_KEY` (نص عشوائي طويل) و`TECHNTING_CMS_ALLOWED_HOSTS`
   و`TECHNTING_CMS_CSRF_ORIGINS` و`TECHNTING_CMS_ADMIN_URL` و`TECHNTING_CMS_VAR_DIR` و`TECHNTING_CMS_OUTPUT_DIR`، ثم `chmod 600 .env`.
3. ‏`.venv/bin/python manage.py migrate` ثم `.venv/bin/python manage.py collectstatic --noinput`
4. شغّلوا gunicorn (الأمر موجود في `deploy/technting-cms.service`) والمؤقتين، واضبطوا nginx كما في `deploy/README.md`.

## معالج الإعداد

افتحوا عنوان لوحة التحكم. إلى أن يكتمل الإعداد، تقود كل صفحات اللوحة إلى `/setup/`:

1. **الموقع**: اسم الموقع وعنوانه العام.
2. **اللغات**: الإنجليزية فقط، أو العربية فقط، أو الاثنتان مع لغة افتراضية. تكون اللغة الافتراضية في جذر الموقع، والأخرى تحت `/ar/` أو `/en/`.
3. **المسؤول**: اسم المستخدم والبريد الإلكتروني وكلمة المرور. تنطبق قواعد كلمات المرور نفسها المعتمدة في لوحة التحكم: 12 حرفاً
   على الأقل، وألا تكون كلمة شائعة، وألا تشبه اسم المستخدم.
4. **القالب**: القوالب المثبّتة في مجلد `themes/`.
5. **البريد**: خطوة اختيارية فيها خادم SMTP والمنفذ ونوع الأمان (SSL أو STARTTLS) واسم المستخدم وكلمة المرور واسم المرسل.
   يجرّب زر «إرسال رسالة تجريبية» الحساب قبل حفظه، ويؤجّل زر «تخطي هذه الخطوة» البريد إلى وقت لاحق (الإعدادات ثم البريد).
6. **مفتاح الرخصة**: الصقوا المفتاح المجاني من الرسالة التي وصلكم فيها رابط التنزيل. يتحقق منه المعالج مع licenses.technting.com
   لعنوان الموقع في الخطوة الأولى، ويرفض المفتاح الملغى أو غير الصالح أو المستخدم في موقع آخر (املؤوا نموذج التنزيل مرة أخرى
   لتحصلوا على مفتاح جديد). وإذا تعذّر الوصول إلى خادم الرخص، يُحفظ المفتاح ويُتحقق منه لاحقاً. وتغيّرونه بعد ذلك من الإعدادات ثم الرخصة.
7. **الإنهاء**: راجعوا الملخص، واختاروا «إضافة محتوى تجريبي» إن أردتم صفحة رئيسية وصفحة خصوصية وقائمة الترويسة، ثم اضغطوا «إنهاء الإعداد».

بعد ذلك ينشئ المعالج حساب المسؤول، ويحفظ اللغات وحساب البريد (تُشفَّر كلمة المرور بالطريقة نفسها المستخدمة في الإعدادات ثم البريد)،
ويكتب اسم الموقع وعنوانه والقالب في `.env` (أو في `VAR_DIR/site.env`)، ثم يسجّل دخولكم وينشر الموقع. ومن تلك اللحظة يعيد `/setup/` الرمز 404.

الحماية: لا يوجد المعالج إلا ما دام لا يوجد أي مستخدم ولم يُسجَّل اكتمال الإعداد، وكل نماذجه محمية من CSRF، وعدد المحاولات
والرسائل التجريبية محدود لكل عنوان، وإذا ضُبط `TECHNTING_CMS_SETUP_TOKEN` يُطلب المفتاح مرة واحدة. ثبّتوا على خادم لا يصل إليه
غيركم بعد، أو احتفظوا بمفتاح الإعداد، وأكملوا المعالج فوراً.

## بعد الإعداد

- الإعدادات: بريد التواصل، وصندوق العملاء المحتملين، وفرض التحقق بخطوتين على جميع المستخدمين، وزر الترويسة.
- المستخدمون: ادعوا المحررين والكتّاب وفريق المبيعات.
- الإضافات: فعّلوا Technting Shield (يبدأ في وضع التعلّم) وTechnting Backup للنسخ خارج الخادم.
- الإعدادات ثم التحديثات: اضغطوا «البحث عن تحديثات». تسأل لوحة التحكم technting.com عن أحدث إصدار منشور
  (`TECHNTING_CMS_UPDATE_FEED`) وتثبّت ملفه بزر «التحديث الآن». ولا يُرسل إلا رقم النسخة التي تشغّلونها.
  وللتحديث من مستودع Git خاص بكم بدلاً من ذلك، اضبطوا `TECHNTING_CMS_UPDATE_REMOTE` في `.env` على ذلك المستودع.

## الترقية

- التثبيت عبر systemd: من الإعدادات ثم التحديثات (نسخة احتياطية، ثم الشيفرة الجديدة، ثم الترحيلات، ثم إعادة التحميل، ثم النشر، مع
  رجوع تلقائي عند أي خطأ)، أو فكّوا الإصدار الجديد وشغّلوا `sudo bash install.sh` مرة أخرى؛ فهو يسأل قبل استبدال الشيفرة،
  ويبقى `.env` و`.venv` والبيانات كما هي.
- ‏Docker: فكّوا الإصدار الجديد أو نفّذوا `git pull`، ثم `docker compose up -d --build`.
- اقرؤوا `CHANGELOG.md` قبل كل ترقية.

## النسخ الاحتياطي والاسترجاع

تعمل النسخ الاحتياطية كل ليلة (`backup --keep 14`): لقطة من قاعدة البيانات، والملفات المرفوعة، وملف بيان فيه بصمات SHA-256.
اللقطة هي `technting_cms.sqlite3` مع SQLite (عبر واجهة النسخ الاحتياطي المباشر في SQLite)، و`database.sql.gz` مع MySQL أو
MariaDB (‏`mysqldump --single-transaction --routines`) أو PostgreSQL (‏`pg_dump`). وتأخذ أدوات التصدير كلمة المرور من ملف
خيارات مؤقت أو من متغيرات البيئة، ولا تظهر أبداً في سطر الأوامر. وتظهر النسخ في الإعدادات ثم النسخ الاحتياطية. للاسترجاع في
تثبيت systemd:

```bash
sudo systemctl stop technting-cms
sudo -u technting /home/technting/technting-cms/.venv/bin/python /home/technting/technting-cms/manage.py restore_backup <folder> --yes
sudo -u technting /home/technting/technting-cms/.venv/bin/python /home/technting/technting-cms/manage.py publish
sudo systemctl start technting-cms
```

يتحقق `restore_backup` من كل البصمات أولاً. مع SQLite ينقل ملف قاعدة البيانات الحالي جانباً، ومع MySQL أو MariaDB أو
PostgreSQL يصدّر قاعدة البيانات الحالية أولاً إلى `VAR_DIR/database-before-restore-<stamp>/`، ثم يحمّل النسخة الاحتياطية
بالأداة `mysql` أو `psql`. والنسخ المأخوذة قبل الإصدار 0.3.0 نسخ SQLite، وما زال استرجاعها ممكناً.

وفي Docker: `docker compose stop app scheduler`، ثم
`docker compose run --rm app manage restore_backup /data/backups/technting-cms/<folder> --yes`،
ثم `docker compose run --rm app manage publish`، ثم `docker compose start app scheduler`.

## تشغيل نسخة تجريبية عامة

يحوّل الإعداد `TECHNTING_CMS_DEMO_MODE=1` التثبيت إلى نسخة تجريبية عامة يجرّبها أي شخص بحساب مشترك. خصّصوا لها خادماً
مستقلاً أو حزمة Docker مستقلة، ولا تفعّلوه أبداً على موقعكم الحقيقي، لأن الأمر `demo_reset` يستبدل قاعدة البيانات
والملفات المرفوعة والموقع المنشور.

ما الذي يتغيّر في الوضع التجريبي:

- تعرض صفحة الدخول بيانات الحساب التجريبي، وتظهر في كل صفحات لوحة التحكم لافتة بالعربية والإنجليزية تنبّه إلى أن
  النسخة يُعاد ضبطها كل ساعتين، وأن على الزوار ألا يُدخلوا بيانات شخصية حقيقية.
- الحساب التجريبي حساب مدير، فيستطيع الزوار تجربة الصفحات والمجموعات والوسائط والقوائم ونظام إدارة العملاء والنماذج
  وصندوق الوارد وإعدادات الموقع وأداة البحث والاستبدال. أما الإجراءات التالية فتُرفض مع رسالة توضيحية: التحديث الذاتي،
  والنسخ الاحتياطي (الإنشاء والتنزيل والاسترجاع والنسخ خارج الخادم)، وإعدادات البريد، وإدارة المستخدمين (الإنشاء
  والدعوة وتغيير الأدوار والإيقاف)، وتغيير كلمة مرور الحساب وتفعيل التحقق بخطوتين، وحسابات التواصل الاجتماعي، وفحص
  الأمان وTechnting Shield، وتغيير الإضافات، وتحديث بيانات Technting SEO، وفحص الروابط الخارجية، والاستيراد إلى نظام إدارة العملاء.
- لا يغادر الخادمَ أي بريد: تُكتب الرسائل في سجل الخادم فقط، وتبقى الاستفسارات تصل إلى صندوق الوارد.
- لا اتصالات خارجية: تتوقف بهدوء كل الميزات التي تتصل بخوادم أخرى (الـ webhooks وIndexNow وقوائم التهديدات في Shield
  واستعلامات Cloudflare والسمعة وPwned Passwords وTechnting SEO وGoogle Drive وS3)، ولا يُسمح إلا بعناوين الموقع نفسه.
- الرفع: ملفات JPEG وPNG وWebP وGIF وPDF فقط، بحجم لا يزيد على 5 ميغابايت، ويُتحقق من المحتوى ومن الامتداد معاً
  (وتُرفض ملفات PDF التي تحتوي على نصوص برمجية)، وبمجموع 300 ميغابايت حتى إعادة الضبط التالية.
- أقسام HTML المخصصة لا تظهر في قائمة الأقسام، ويُرفض حفظها، ولا تُنشر أبداً. ويُنظَّف النص المنسّق كالمعتاد.
- ترسل لوحة التحكم الترويسة `X-Robots-Tag: noindex, nofollow`، ويمنع ملف `robots.txt` المنشور محركات البحث من الموقع كله.

أضيفوا إلى `.env`:

```
TECHNTING_CMS_DEMO_MODE=1
TECHNTING_CMS_DEMO_USER=<اسم المستخدم التجريبي>
TECHNTING_CMS_DEMO_PASSWORD=<كلمة المرور التجريبية>
```

كلمة المرور هذه علنية عن قصد لأنها تظهر في صفحة الدخول، فلا تستخدموها في أي مكان آخر.

يبني الأمر `manage.py demo_reset` نسخة تجريبية جديدة في مجلد بجوار مجلد البيانات (قاعدة بيانات جديدة فيها المحتوى
التجريبي والحساب التجريبي مع اعتبار الإعداد مكتملاً، ونسخة منشورة من الموقع)، ثم يضعها في مكانها: تُنسخ قاعدة البيانات
إلى الملف المستخدم في معاملة واحدة، ويُبدَّل مجلد الوسائط، وتُحدَّث ملفات الموقع المنشور في مكانها فلا يرى nginx مجلداً
فارغاً، وتنتهي كل الجلسات، وتُمسح الذاكرة المؤقتة. وإذا فشل البناء لم يتغيّر شيء في النسخة العاملة. ولا يعمل الأمر إلا
في الوضع التجريبي (يتجاوز الخيار `--force` هذا الشرط، فلا تستخدموه على موقع حقيقي)، ولا يعمل إلا مع قاعدة بيانات SQLite
الافتراضية، فأبقوا النسخة التجريبية على SQLite.

في التثبيت عبر systemd، يعيد المؤقّت ضبط النسخة كل ساعتين (عند الساعات الزوجية)، ويُسمح لكل تشغيل بعشر دقائق كحد أقصى:

```bash
sudo cp deploy/technting-cms-demo-reset.service deploy/technting-cms-demo-reset.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now technting-cms-demo-reset.timer
sudo systemctl start technting-cms-demo-reset.service    # أول نسخة تجريبية، الآن
sudo systemctl disable --now technting-cms-backup.timer  # النسخة التجريبية لا تحتاج إلى نسخ احتياطي ليلي
```

السجلات: `journalctl -u technting-cms-demo-reset`.

ومع Docker، أضيفوا ملف الوضع التجريبي:

```bash
docker compose -f docker-compose.yml -f deploy/docker/docker-compose.demo.yml up -d --build
```

يفعّل هذا الملف الوضع التجريبي، ويحدّ ذاكرة حاوية لوحة التحكم بـ 768 ميغابايت، ويجعل حاوية الجدولة تعيد بناء النسخة
التجريبية عند تشغيلها ثم كل ساعتين (ويُوقَف كل تشغيل بعد عشر دقائق)، مع استمرارها في نشر المقالات المجدولة. وتستمع لوحة
التحكم على `127.0.0.1:18150` والموقع على `127.0.0.1:18151`، ليكون أمامهما خادم وكيل يوفّر HTTPS.
لإعادة الضبط يدوياً:
`docker compose -f docker-compose.yml -f deploy/docker/docker-compose.demo.yml run --rm app manage demo_reset`،
والسجلات: `docker compose logs scheduler`.

## حل المشكلات

| المشكلة | الحل |
|---|---|
| رسالة «CSRF verification failed» أو تكرار صفحة الدخول عبر http عادي | استخدموا https، أو ضعوا `TECHNTING_CMS_HTTPS=0` مؤقتاً أثناء التجربة على عنوان في الشبكة |
| رسالة «Bad Request (400)» | أضيفوا اسم المضيف إلى `TECHNTING_CMS_ALLOWED_HOSTS` |
| المعالج يطلب مفتاح إعداد | المفتاح هو قيمة `TECHNTING_CMS_SETUP_TOKEN` في `.env` |
| حقل في المعالج للقراءة فقط | القيمة مضبوطة في بيئة الخادم (systemd أو Docker)، فغيّروها هناك |
| نسيان كلمة المرور | نفّذوا `manage.py changepassword <username>` على الخادم |
| حظر من Technting Shield | نفّذوا `manage.py shield learning` |
| رسالة «TECHNTING_CMS_DB_ENGINE=mysql needs ...» عند التشغيل | أضيفوا قيم `TECHNTING_CMS_DB_*` الناقصة إلى `.env` |
| رسالة «Error loading MySQLdb module» | ثبّتوا المشغّل: `pip install -r requirements-mysql.txt` (راجعوا [قاعدة البيانات](#قاعدة-البيانات)) |
| فشل النسخ الاحتياطي مع «mysqldump was not found» أو «pg_dump was not found» | ثبّتوا `mariadb-client` أو `postgresql-client` |

</div>
