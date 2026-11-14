"""Dashboard interface language (English / Arabic).

The editor picks a language from the sidebar; it is stored in the session. Strings are
looked up by their English text, so an untranslated string simply stays in English.
Theme labels (block, field and collection names) are translated by the theme's
"admin_strings" map.
"""
AR = {
    # navigation and shell
    "Dashboard": "لوحة التحكم", "Content": "المحتوى", "Pages": "الصفحات", "Media": "الوسائط", "Site": "الموقع",
    "Inbox": "صندوق الوارد", "Menus": "القوائم", "Settings": "الإعدادات", "Users": "المستخدمون", "My account": "حسابي",
    "Signed in as": "مسجّل الدخول باسم", "Sign out": "تسجيل الخروج", "View site ↗": "عرض الموقع ↗", "Publish site": "نشر الموقع",
    "Rebuild and publish the whole site": "إعادة بناء الموقع كاملاً ونشره", "Interface language": "لغة الواجهة",
    # dashboard
    "Media files": "ملفات الوسائط", "Recently edited pages": "آخر الصفحات المعدّلة", "+ New page": "+ صفحة جديدة",
    "No pages yet.": "لا توجد صفحات بعد.", "Publishing": "النشر", "Last publish:": "آخر نشر:", "OK": "تم", "Failed": "فشل",
    "Error": "خطأ", "ago": "مضت", "The site has not been published from Technting CMS yet.": "لم يُنشر الموقع من Technting CMS بعد.",
    "Recently edited records": "آخر السجلات المعدّلة",
    # pages
    "Title": "العنوان", "Address": "الرابط", "Template": "القالب", "Languages": "اللغات", "Delete": "حذف",
    "Search pages": "البحث في الصفحات", "Search": "بحث", "No pages found.": "لا توجد صفحات مطابقة.",
    "Delete this page in every language?": "حذف هذه الصفحة بكل لغاتها؟",
    "Areas and use cases have their own pages, generated from the Areas and Use cases collections.":
        "للمجالات وحالات الاستخدام صفحات خاصة تُولَّد تلقائياً من مجموعتي المجالات وحالات الاستخدام.",
    "New page": "صفحة جديدة", "Address (slug)": "الرابط المختصر (slug)", "Created from the title if empty": "يُنشأ من العنوان إذا تُرك فارغاً",
    "Language": "اللغة", "Create and edit": "إنشاء وتعديل", "Page title": "عنوان الصفحة", "(home page)": "(الصفحة الرئيسية)",
    "Preview ↗": "معاينة ↗", "Live page ↗": "الصفحة المنشورة ↗", "Publish": "نشر", "Status:": "الحالة:",
    "Goes live": "تُنشر في", "Update": "تحديث", "Save draft": "حفظ كمسودة", "Schedule": "جدولة النشر", "Set": "تعيين",
    "Unpublish": "إلغاء النشر", "Take this language version offline?": "إلغاء نشر هذه النسخة اللغوية؟", "Page": "الصفحة",
    "Parent page": "الصفحة الأم", "None": "بدون", "Search & sharing": "محركات البحث والمشاركة", "SEO title": "عنوان SEO",
    "Meta description": "وصف SEO", "Share image (1200×630)": "صورة المشاركة (1200×630)",
    "Hide from search engines": "إخفاء عن محركات البحث", "Revisions": "النسخ السابقة", "Restore": "استعادة",
    "Restore this revision?": "استعادة هذه النسخة؟", "system": "النظام", "Template settings": "إعدادات القالب",
    "Draft": "مسودة", "Published": "منشورة", "Scheduled": "مجدولة",
    "This page has no {lang} version yet. The layout below is copied from the existing version: translate the text, then save.":
        "لا توجد نسخة من هذه الصفحة باللغة {lang} بعد. التصميم أدناه منسوخ من النسخة الموجودة: ترجموا النصوص ثم احفظوا.",
    # collections
    "+ New": "+ جديد", "Key": "المعرّف", "Status": "الحالة", "Order": "الترتيب", "Hidden": "مخفي", "Nothing here yet.": "لا يوجد شيء هنا بعد.",
    "Each record has its own page at": "لكل سجل صفحة خاصة على الرابط", "text": "النصوص",
    "Shared by all languages": "مشترك بين كل اللغات", "Visible on the site": "ظاهر على الموقع",
    "Save and publish": "حفظ ونشر", "Saving rebuilds the site, so the change is live in a few seconds.": "الحفظ يعيد بناء الموقع، فيظهر التغيير خلال ثوانٍ.",
    "Danger zone": "منطقة الخطر", "All": "الكل", "No translation yet. The fields show the default language as a starting point: translate them, then save.":
        "لا توجد ترجمة بعد. تعرض الحقول نصوص اللغة الأساسية لتبدؤوا منها: ترجموها ثم احفظوا.",
    "A short, permanent identifier (letters, numbers, dashes).": "معرّف قصير ودائم (أحرف وأرقام وشرطات).",
    "It becomes part of the address:": "ويصبح جزءاً من الرابط:",
    # media
    "Media library": "مكتبة الوسائط", "Drop images or PDFs here, or": "اسحبوا الصور أو ملفات PDF إلى هنا، أو",
    "choose files": "اختاروا ملفات", "JPEG, PNG, WebP, GIF and PDF up to 20 MB. Images get WebP copies automatically.":
        "JPEG وPNG وWebP وGIF وPDF حتى 20 ميغابايت، وتُنشأ نسخ WebP للصور تلقائياً.",
    "Search media": "البحث في الوسائط", "Details": "التفاصيل", "Select a file to edit its title and alternative text.": "اختاروا ملفاً لتعديل عنوانه ونصه البديل.",
    "Size": "الحجم", "Uploaded": "تاريخ الرفع", "Alternative text": "النص البديل", "Save": "حفظ",
    "Delete this file permanently?": "حذف هذا الملف نهائياً؟", "Deleted.": "تم الحذف.", "Uploading…": "جارٍ الرفع…",
    "file(s) uploaded.": "ملف/ملفات رُفعت.", "Saved. Publish the site to update pages that use it.": "تم الحفظ. انشروا الموقع لتحديث الصفحات التي تستخدمه.",
    # menus
    "The header menu shows in the top bar of every page. The footer menu is made of columns, each with its own links. Use #contact as the address to open the contact form.":
        "تظهر قائمة الرأس في الشريط العلوي لكل صفحة. وتتكون قائمة التذييل من أعمدة لكل منها روابطها. استخدموا ‎#contact‎ رابطاً لفتح نموذج التواصل.",
    "Header menu": "قائمة الرأس", "Footer menu": "قائمة التذييل", "Save menus and publish": "حفظ القوائم ونشرها",
    "Links": "الروابط", "Columns": "الأعمدة", "Column title": "عنوان العمود", "Text": "النص", "Opens the contact form": "يفتح نموذج التواصل",
    "link": "رابطاً", "column": "عموداً",
    # settings
    "Contact email": "بريد التواصل", "Header button text": "نص زر الرأس", "Header button address": "رابط زر الرأس",
    "Theme": "المظهر", "Active theme": "المظهر الحالي", "Page templates": "قوالب الصفحات", "Block types": "أنواع الأقسام",
    "Collections": "المجموعات", "Themes live in the themes/ folder of Technting CMS and are changed by a developer.": "توجد ملفات المظهر في مجلد themes/ داخل Technting CMS، ويعدّلها مطوّر.",
    "Redirects": "التحويلات", "Send an old address to a new one (301). Useful when you rename a page.": "تحويل رابط قديم إلى رابط جديد (301)، ويفيد عند تغيير اسم صفحة.",
    "Add": "إضافة", "Remove": "إزالة", "No redirects.": "لا توجد تحويلات.",
    # users and account
    "User": "المستخدم", "Email": "البريد الإلكتروني", "Role": "الدور", "Last sign-in": "آخر دخول", "you": "أنت",
    "Administrator": "مدير", "Editor": "محرّر", "No access": "بلا صلاحية", "Deactivated": "معطّل", "Deactivate": "تعطيل",
    "Activate": "تفعيل", "never": "لم يسجّل الدخول", "Add a user": "إضافة مستخدم", "Username": "اسم المستخدم", "Password": "كلمة المرور",
    "At least 12 characters.": "12 حرفاً على الأقل.", "Editor: pages, collections, media, menus": "محرّر: الصفحات والمجموعات والوسائط والقوائم",
    "Administrator: everything, including users and settings": "مدير: كل شيء بما فيه المستخدمون والإعدادات", "Create user": "إنشاء المستخدم",
    "Change password": "تغيير كلمة المرور", "Current password": "كلمة المرور الحالية", "New password": "كلمة المرور الجديدة",
    "At least 12 characters, not a common password.": "12 حرفاً على الأقل، وليست كلمة مرور شائعة.",
    # inbox
    "Export CSV": "تصدير CSV", "Open": "مفتوحة", "New": "جديدة", "Read": "مقروء", "Archived": "مؤرشف",
    "Search name, email, message": "البحث في الاسم أو البريد أو الرسالة", "From": "المرسل", "Interest": "الاهتمام",
    "Message": "الرسالة", "Received": "تاريخ الاستلام", "no email": "بلا بريد", "No enquiries here.": "لا توجد استفسارات هنا.",
    "Enquiries from the website contact form are saved here. Email copies are off until Gmail is connected on the server (setup_gmail_smtp.sh).":
        "تُحفظ هنا الاستفسارات الواردة من نموذج التواصل. نسخ البريد متوقفة حتى يُربط Gmail على الخادم (setup_gmail_smtp.sh).",
    "Enquiry from": "استفسار من", "Reply by email": "الرد بالبريد", "Back to inbox": "العودة إلى صندوق الوارد", "Name": "الاسم",
    "Organisation": "المؤسسة", "Phone": "الهاتف", "Not provided": "غير مذكور", "Not specified": "غير محدد", "Sent from": "أُرسل من",
    "emailed to the team": "أُرسل إلى بريد الفريق", "not emailed": "لم يُرسل بالبريد", "Handling": "المتابعة",
    "Internal note (not sent to the client)": "ملاحظة داخلية (لا تُرسل للعميل)", "Archive": "أرشفة", "Move back to open": "إلغاء الأرشفة",
    "Mark as new": "تحديد كجديد", "Delete permanently": "حذف نهائياً",
    "Delete this enquiry permanently? This also removes the personal data it contains.": "حذف هذا الاستفسار نهائياً؟ سيُحذف معه ما يتضمنه من بيانات شخصية.",
    # login
    "Sign in": "تسجيل الدخول",
    "Keep me signed in for 30 days": "تذكّرني لمدة 30 يوماً",
}

AR.update({
    "Two-step verification": "التحقق بخطوتين", "Enter the 6-digit code from your authenticator app.": "أدخلوا الرمز المكوّن من 6 أرقام من تطبيق المصادقة.",
    "Code": "الرمز", "Verify and sign in": "التحقق وتسجيل الدخول", "Lost your phone? Enter one of your recovery codes instead.": "فقدتم هاتفكم؟ أدخلوا أحد رموز الاسترداد بدلاً من ذلك.",
    "Back to sign in": "العودة لتسجيل الدخول", "Too many attempts. Wait 15 minutes and try again.": "محاولات كثيرة. انتظروا 15 دقيقة ثم حاولوا مجدداً.",
    "That code is not correct. Use the current code from your app, or a recovery code.": "الرمز غير صحيح. استخدموا الرمز الحالي من التطبيق أو رمز استرداد.",
    "Your recovery codes": "رموز الاسترداد", "Copy codes": "نسخ الرموز", "I saved them": "حفظتها",
    "Save these codes somewhere safe, such as a password manager. Each code works once if you lose your phone. They are shown only now.":
        "احفظوا هذه الرموز في مكان آمن مثل مدير كلمات المرور. يعمل كل رمز مرة واحدة إذا فقدتم هاتفكم، ولن تظهر مرة أخرى.",
    "On": "مفعّل", "Since": "منذ", "Recovery codes left": "رموز الاسترداد المتبقية", "Code from your app": "الرمز من التطبيق",
    "New recovery codes": "رموز استرداد جديدة", "Turn off": "إيقاف", "Turn off two-step verification?": "إيقاف التحقق بخطوتين؟",
    "This site requires two-step verification. Set it up to continue.": "يتطلب هذا الموقع التحقق بخطوتين. فعّلوه للمتابعة.",
    "Set up two-step verification": "تفعيل التحقق بخطوتين",
    "Install an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, 1Password or similar).": "ثبّتوا تطبيق مصادقة على هاتفكم (Google Authenticator أو Microsoft Authenticator أو 1Password أو ما يشبهها).",
    "In the app, add an account and scan this QR code.": "أضيفوا حساباً في التطبيق وامسحوا رمز QR هذا.",
    "Type the 6-digit code the app shows, then confirm.": "اكتبوا الرمز المكوّن من 6 أرقام الظاهر في التطبيق، ثم أكّدوا.",
    "Cannot scan? Enter this key in the app:": "لا يمكنكم المسح؟ أدخلوا هذا المفتاح في التطبيق:", "Confirm": "تأكيد",
    "Two-step verification is on.": "تم تفعيل التحقق بخطوتين.", "Two-step verification is off.": "تم إيقاف التحقق بخطوتين.",
    "That code is not correct. Scan the QR code again and use the newest code.": "الرمز غير صحيح. امسحوا رمز QR مجدداً واستخدموا أحدث رمز.",
    "Your password or code is not correct.": "كلمة المرور أو الرمز غير صحيح.", "Two-step verification is required on this site.": "التحقق بخطوتين إلزامي على هذا الموقع.",
    "Require two-step verification for every user": "إلزام كل المستخدمين بالتحقق بخطوتين",
    "Turn on two-step verification for your own account first.": "فعّلوا التحقق بخطوتين لحسابكم أولاً.",
    "Protect your account with a code from your phone in addition to your password.": "احموا حسابكم برمز من هاتفكم إلى جانب كلمة المرور.",
    "Manage two-step verification": "إدارة التحقق بخطوتين",
})

AR.update({
    # roles and review
    "Author": "كاتب", "Editor": "محرر", "Administrator": "مدير",
    "Author: writes blog posts and sends them for review": "كاتب: يكتب المقالات ويرسلها للمراجعة",
    "Role updated.": "تم تحديث الدور.", "You cannot change your own role.": "لا يمكنكم تغيير دوركم بأنفسكم.",
    "Save draft": "حفظ المسودة", "Send for review": "إرسال للمراجعة", "Sent for review": "أُرسلت للمراجعة", "Draft": "مسودة",
    "An editor checks your draft and publishes it. You can keep editing until then.": "يراجع المحرر مسودتكم وينشرها، ويمكنكم مواصلة التعديل حتى ذلك الحين.",
    "Sent for review. An editor will check and publish it.": "أُرسلت للمراجعة. سيراجعها المحرر وينشرها.",
    "Sent for review by": "أرسلها للمراجعة", "Tick Visible and save to publish it.": "فعّلوا «ظاهر على الموقع» واحفظوا لنشرها.",
    "Waiting for your review": "بانتظار مراجعتكم",
    "Only your own drafts can be edited. Ask an editor to change a published post.": "يمكنكم تعديل مسوداتكم فقط. اطلبوا من المحرر تعديل المقالات المنشورة.",
    # SEO check
    "SEO check": "فحص SEO", "Title length 30 to 60 characters": "طول العنوان بين 30 و60 حرفاً",
    "Description 70 to 160 characters": "طول الوصف بين 70 و160 حرفاً", "Focus keyword set": "الكلمة المفتاحية محددة",
    "Keyword in the SEO title": "الكلمة المفتاحية في عنوان SEO", "Keyword in the description": "الكلمة المفتاحية في الوصف",
    "Keyword in the first paragraph": "الكلمة المفتاحية في الفقرة الأولى", "Keyword in the address": "الكلمة المفتاحية في الرابط",
    "At least 800 words": "800 كلمة على الأقل", "Two or more H2 subheadings": "عنوانان فرعيان (H2) أو أكثر",
    "Two or more links to our own pages": "رابطان أو أكثر إلى صفحاتنا", "Links to an authoritative source": "رابط إلى مصدر موثوق",
    "Images in the text have alt text": "الصور داخل النص لها نص بديل", "Cover image with alt text": "صورة غلاف لها نص بديل",
    "Three or more FAQ answers": "ثلاثة أسئلة شائعة أو أكثر", "Translated into every site language": "مترجم إلى كل لغات الموقع",
    "Checked when you save. Aim for green on the main points; not every item applies to every page.": "يُحدَّث الفحص عند الحفظ. اسعوا إلى اللون الأخضر في النقاط الرئيسية؛ لا ينطبق كل بند على كل صفحة.",
})

AR.update({"Publish at (optional)": "موعد النشر (اختياري)", "Scheduled": "مجدولة",
           "Leave empty to publish now. With a date, a visible entry appears on the site at that time.": "اتركوه فارغاً للنشر فوراً. وإذا حددتم موعداً يظهر السجل المرئي على الموقع في ذلك الوقت.",
           "Scheduled: it appears on the site at": "مجدول: يظهر على الموقع في"})

AR.update({"Site health": "سلامة الموقع", "items to check": "عناصر للمراجعة", "important": "مهمة", "No problems found": "لا توجد مشكلات",
           "pages checked": "صفحة فُحصت", "Broken internal link": "رابط داخلي معطّل", "Missing page title": "لا يوجد عنوان للصفحة",
           "Title longer than 70 characters": "عنوان أطول من 70 حرفاً", "Same title on several pages": "العنوان نفسه في عدة صفحات",
           "Missing meta description": "لا يوجد وصف SEO", "Missing canonical link": "لا يوجد رابط canonical", "No H1 heading": "لا يوجد عنوان H1",
           "More than one H1 heading": "أكثر من عنوان H1", "Images without alt text": "صور بلا نص بديل",
           "Checked on every publish, before the site goes live.": "يُفحص الموقع مع كل نشر قبل أن يصل إلى الزوار.",
           "Last check": "آخر فحص", "Page": "الصفحة", "Detail": "التفاصيل", "high": "مرتفعة", "medium": "متوسطة", "low": "منخفضة",
           "Publish the site once to run the first check.": "انشروا الموقع مرة واحدة لإجراء أول فحص."})

AR.update({"Activity": "سجل النشاط", "When": "الوقت", "Action": "الإجراء", "Target": "العنصر", "IP address": "عنوان IP", "All users": "كل المستخدمين", "All actions": "كل الإجراءات", "Filter": "تصفية", "Who did what in the dashboard. Kept for one year.": "ما فعله كل مستخدم في لوحة التحكم. يُحتفظ بالسجل لمدة سنة.", "No activity yet.": "لا يوجد نشاط بعد."})

AR.update({"External links": "الروابط الخارجية", "broken": "معطّلة", "links": "رابط", "Check now": "افحص الآن", "Link": "الرابط",
           "Result": "النتيجة", "Used in": "مستخدم في", "blocked": "محجوب", "All external links work": "كل الروابط الخارجية تعمل",
           "Links to outside sources in pages and articles, checked once a month. Blocked means the site refuses automated checks; open it yourself to confirm.":
               "روابط المصادر الخارجية في الصفحات والمقالات، وتُفحص مرة كل شهر. «محجوب» يعني أن الموقع يرفض الفحص الآلي، فافتحوه بأنفسكم للتأكد.",
           "Checking external links. Refresh this page in a minute or two.": "جارٍ فحص الروابط الخارجية. حدّثوا هذه الصفحة بعد دقيقة أو دقيقتين."})

AR["Welcome. Turn on two-step verification to protect your account."] = "أهلاً بكم. فعّلوا التحقق بخطوتين لحماية حسابكم."

AR.update({
    "Email settings": "إعدادات البريد", "Email settings removed.": "حُذفت إعدادات البريد.", "Test email sent to": "أُرسلت رسالة تجريبية إلى",
    "Sending failed:": "فشل الإرسال:", "Enter the Gmail address and its app password.": "أدخلوا عنوان Gmail وكلمة مرور التطبيق الخاصة به.",
    "Gmail rejected the sign-in. Check the address and use an app password (2-Step Verification must be on).":
        "رفض Gmail تسجيل الدخول. تأكدوا من العنوان واستخدموا كلمة مرور تطبيق (يجب تفعيل التحقق بخطوتين في حساب Google).",
    "Could not reach Gmail:": "تعذّر الاتصال بـ Gmail:", "Gmail sign-in works. Email settings saved.": "تسجيل الدخول إلى Gmail يعمل، وحُفظت إعدادات البريد.",
    "This user has already set a password.": "عيّن هذا المستخدم كلمة مروره من قبل.", "Add an email address for this user first.": "أضيفوا بريداً إلكترونياً لهذا المستخدم أولاً.",
    "Set up email first (Settings → Email).": "فعّلوا إرسال البريد أولاً (الإعدادات ← البريد).", "Invitation sent to": "أُرسلت الدعوة إلى",
    "Send invitation": "إرسال الدعوة", "Invited, not signed in yet": "مدعو، لم يسجّل دخوله بعد",
    "Account that sends invitations and copies of website enquiries.": "الحساب الذي يرسل الدعوات ونسخ استفسارات الموقع.",
    "Email delivery": "إرسال البريد", "Status": "الحالة", "Working": "يعمل", "Not set up": "غير مُفعّل",
    "Sender": "المرسل", "Gmail address": "عنوان Gmail", "App password": "كلمة مرور التطبيق",
    "Sender name": "اسم المرسل", "Test and save": "اختبار وحفظ", "Send a test email to": "إرسال رسالة تجريبية إلى",
    "Send test email": "إرسال رسالة تجريبية", "Remove email settings": "حذف إعدادات البريد",
    "Leave empty to keep the saved password.": "اتركوه فارغاً للإبقاء على كلمة المرور المحفوظة.",
    "How to get an app password": "كيف تحصلون على كلمة مرور التطبيق",
    "Sign in to the Gmail account that will send the emails.": "سجّلوا الدخول إلى حساب Gmail الذي سيرسل الرسائل.",
    "Turn on 2-Step Verification in the Google account (required for app passwords).": "فعّلوا التحقق بخطوتين في حساب Google (مطلوب لكلمات مرور التطبيقات).",
    "Open myaccount.google.com/apppasswords, name it Technting CMS and press Create.": "افتحوا myaccount.google.com/apppasswords، وسمّوها Technting CMS، واضغطوا «إنشاء».",
    "Copy the 16 letters here. Google shows them only once.": "انسخوا الرمز المكوّن من 16 حرفاً والصقوه هنا، فـ Google يعرضه مرة واحدة فقط.",
    "The password is stored encrypted and is never shown again. Technting CMS tests the sign-in before saving.":
        "تُحفظ كلمة المرور مشفّرة ولا تُعرض مرة أخرى، ويختبر Technting CMS تسجيل الدخول قبل الحفظ.",
    "Remove email settings?": "حذف إعدادات البريد؟", "from": "من", "configured in .env on the server": "محدد في ملف .env على الخادم",
})

AR["Enquiries from the website contact form are saved here. Email copies are off until email is set up."] = "تُحفظ هنا الاستفسارات الواردة من نموذج التواصل. نسخ البريد متوقفة حتى يُفعّل إرسال البريد."
AR["Email"] = "البريد"

AR.update({"Plugins": "الإضافات", "Save plugins and publish": "حفظ الإضافات ونشرها",
    "Plugins add features to the site. Turn them on or off and fill in their settings here. New plugins are installed by a developer.":
        "تضيف الإضافات ميزات إلى الموقع. فعّلوها أو أوقفوها واملؤوا إعداداتها هنا، ويثبّت المطوّر الإضافات الجديدة."})

AR.update({
    # stats
    "Stats": "الإحصائيات", "7 days": "7 أيام", "30 days": "30 يوماً", "90 days": "90 يوماً", "12 months": "12 شهراً",
    "Stats are off. Turn on the Site stats plugin to start counting visits.": "الإحصائيات متوقفة. فعّلوا إضافة «إحصائيات الموقع» ليبدأ عدّ الزيارات.",
    "on the site now": "على الموقع الآن",
    "No cookies and no IP addresses are stored. Your own visits while signed in are not counted.":
        "لا نحفظ ملفات تعريف الارتباط ولا عناوين IP. ولا تُحسب زياراتكم وأنتم مسجّلون في لوحة التحكم.",
    "Visitors": "الزوار", "Page views": "مشاهدات الصفحات", "Pages per visit": "صفحات لكل زيارة", "Enquiries": "الاستفسارات",
    "Compared with the period before": "مقارنة بالفترة السابقة", "Visitors per day": "الزوار يومياً", "Visitors per week": "الزوار أسبوعياً",
    "peak": "الأعلى", "Top pages": "أكثر الصفحات زيارة", "Views": "المشاهدات", "No visits in this period yet.": "لا توجد زيارات في هذه الفترة بعد.",
    "Where visitors come from": "من أين يأتي الزوار", "Sources": "المصادر", "Countries": "الدول", "Devices and languages": "الأجهزة واللغات",
    "Site language": "لغة الموقع", "Campaigns": "الحملات", "Direct": "مباشرة", "Search engines": "محركات البحث",
    "AI assistants": "مساعدات الذكاء الاصطناعي", "Social media": "مواقع التواصل", "Other websites": "مواقع أخرى",
    "Mobile": "الجوال", "Tablet": "الجهاز اللوحي", "Desktop": "الكمبيوتر", "Unknown": "غير معروف",
    "Pages not found (404)": "صفحات غير موجودة (404)", "Send each one to the right page with a redirect.": "حوّلوا كل رابط منها إلى الصفحة الصحيحة.",
    "Add redirect": "إضافة تحويل", "No visitor reached a missing page in this period.": "لم يصل أي زائر إلى صفحة غير موجودة في هذه الفترة.",
    "Search terms and positions on Google are in Google Search Console.": "كلمات البحث وترتيب الموقع في Google موجودة في Google Search Console.",
    "Last 7 days": "آخر 7 أيام",
    # calendar
    "Calendar": "التقويم", "Previous month": "الشهر السابق", "Next month": "الشهر التالي", "Today": "اليوم",
    "Waiting for review": "بانتظار المراجعة", "Draft": "مسودة",
    "Drag a scheduled or draft item to another day to change its publication date. Published items stay where they are.":
        "اسحبوا أي عنصر مجدول أو مسودة إلى يوم آخر لتغيير موعد نشره. العناصر المنشورة تبقى في مكانها.",
    "Sun": "الأحد", "Mon": "الاثنين", "Tue": "الثلاثاء", "Wed": "الأربعاء", "Thu": "الخميس", "Fri": "الجمعة", "Sat": "السبت",
    "January": "يناير", "February": "فبراير", "March": "مارس", "April": "أبريل", "May": "مايو", "June": "يونيو", "July": "يوليو",
    "August": "أغسطس", "September": "سبتمبر", "October": "أكتوبر", "November": "نوفمبر", "December": "ديسمبر",
    "Coming up": "المواعيد القادمة", "Nothing scheduled this month.": "لا يوجد شيء مجدول هذا الشهر.",
    "Drafts without a date": "مسودات بلا موعد", "No drafts waiting.": "لا توجد مسودات بانتظار النشر.",
    "Moved. The new date is saved.": "تم النقل وحُفظ الموعد الجديد.", "Something went wrong.": "حدث خطأ.",
    "Choose a day in the future.": "اختاروا يوماً قادماً.", "Only scheduled items can be moved.": "يمكن نقل العناصر المجدولة والمسودات فقط.",
    # SEO card
    "When shared on LinkedIn or WhatsApp": "شكل المقال عند مشاركته على LinkedIn أو واتساب", "The site's default image": "صورة الموقع الافتراضية",
    "Link ideas": "اقتراحات روابط", "Copy": "نسخ",
    "These pages are mentioned in the text but not linked. Linking them helps readers and search engines.":
        "هذه الصفحات مذكورة في النص لكن بلا رابط. ربطها يفيد القارئ ومحركات البحث.",
    # newsletter (CRM)
    "Newsletter": "النشرة البريدية", "Export subscribers (CSV)": "تصدير المشتركين (CSV)", "Subscribed": "مشترك",
    "Waiting for confirmation": "بانتظار التأكيد", "Unsubscribed": "ألغى الاشتراك", "Language": "اللغة", "Signed up on": "صفحة الاشتراك",
    "Date": "التاريخ", "Nobody here yet.": "لا يوجد أحد هنا بعد.",
    "People who signed up on the website and confirmed from the email we sent them. Confirmed subscribers are added to Contacts with marketing consent. Every newsletter you send must include each person's unsubscribe link (it is in the CSV).":
        "الأشخاص الذين اشتركوا من الموقع وأكّدوا من الرسالة التي أرسلناها لهم. يُضاف المشتركون المؤكَّدون إلى جهات الاتصال مع موافقتهم على التسويق. يجب أن تحمل كل نشرة ترسلونها رابط إلغاء الاشتراك الخاص بكل شخص (موجود في ملف CSV).",
    "If you send from another service, export a fresh list before each send so people who unsubscribed are not emailed.":
        "إذا كنتم ترسلون من خدمة أخرى، صدّروا قائمة جديدة قبل كل إرسال حتى لا تصل الرسائل لمن ألغى اشتراكه.",
    "Subscribed to the newsletter": "اشترك في النشرة البريدية", "Unsubscribed from the newsletter": "ألغى الاشتراك في النشرة البريدية",
    # find and replace
    "Find and replace": "البحث والاستبدال",
    "Change a word or phrase everywhere on the site at once: pages, records and menus. Check the list of matches first. Every changed record keeps a revision you can restore, and the site is published after the change.":
        "غيّروا كلمة أو عبارة في كل الموقع مرة واحدة: الصفحات والسجلات والقوائم. راجعوا قائمة النتائج أولاً. يُحفظ لكل سجل يتغيّر نسخة سابقة يمكن استرجاعها، ويُنشر الموقع بعد التغيير.",
    "Find": "البحث عن", "Replace with": "الاستبدال بـ", "Look in": "البحث في", "Records": "السجلات", "All languages": "كل اللغات",
    "Match case": "مطابقة حالة الأحرف", "Also change links and addresses": "تغيير الروابط والعناوين أيضاً", "Show matches": "عرض النتائج",
    "Replace all matches and publish the site?": "استبدال كل النتائج ونشر الموقع؟", "Replace all": "استبدال الكل",
    "Replaced {n} in {r}.": "تم الاستبدال: {n} في {r}.",
    # backups
    "Backups": "النسخ الاحتياطية", "Back up now": "نسخ احتياطي الآن", "Backup": "النسخة", "Contents": "المحتوى", "Size": "الحجم",
    "Download": "تنزيل", "No backups yet.": "لا توجد نسخ احتياطية بعد.", "Backup created.": "أُنشئت نسخة احتياطية.", "Backup failed:": "فشل النسخ الاحتياطي:",
    "A full backup (database and uploaded files) is made every night and the last 14 are kept on the server. Download one at least once a month and keep it somewhere else, such as a company drive, so the site can be rebuilt even if the server is lost.":
        "تُنشأ كل ليلة نسخة احتياطية كاملة (قاعدة البيانات والملفات المرفوعة)، وتُحفظ آخر 14 نسخة على الخادم. نزّلوا نسخة مرة في الشهر على الأقل واحفظوها في مكان آخر، مثل مساحة تخزين الشركة، حتى يمكن إعادة بناء الموقع حتى لو ضاع الخادم.",
    "Restoring replaces the whole site with the backup, so it is done by a developer on the server": "الاسترجاع يستبدل الموقع كله بالنسخة الاحتياطية، لذلك يقوم به مطوّر على الخادم",
})

# sprint 3 strings; setdefault keeps any wording already chosen for the same English text
for _k, _v in {
    "Sales: CRM, website enquiries and stats; no content editing": "المبيعات: CRM واستفسارات الموقع والإحصائيات، دون تعديل المحتوى",
    # translations
    "Translations": "الترجمات", "Needs attention": "يحتاج إلى انتباه", "Missing translation": "ترجمة ناقصة",
    "May be out of date": "قد تكون قديمة", "Type": "النوع", "Up to date": "محدّثة", "Translate": "ترجمة", "Check": "مراجعة",
    "Everything is translated and up to date.": "كل شيء مترجم ومحدّث.",
    "Pages and records with a missing language, or where the default language was changed after the translation. Open the language to update it.":
        "صفحات وسجلات تنقصها لغة، أو تغيّرت لغتها الأساسية بعد الترجمة. افتحوا اللغة لتحديثها.",
    # weekly summary
    "Weekly summary by email": "ملخص أسبوعي بالبريد", "Send me the weekly summary": "أرسلوا لي الملخص الأسبوعي",
    "Every Sunday morning: visitors, enquiries, new deals and subscribers, what is scheduled this week and anything that needs attention. Sent to":
        "كل صباح أحد: الزوار والاستفسارات والصفقات والمشتركون الجدد، وما هو مجدول هذا الأسبوع، وما يحتاج إلى انتباه. يُرسل إلى",
    "Email is not set up yet, so nothing can be sent.": "لم يُفعّل البريد بعد، لذلك لا يمكن الإرسال.",
    "Your current password is not correct.": "كلمة المرور الحالية غير صحيحة.", "Password changed.": "تم تغيير كلمة المرور.",
    # site health: accessibility and speed
    "Accessibility: page language not set": "سهولة الوصول: لغة الصفحة غير محددة",
    "Accessibility: links with no text or label": "سهولة الوصول: روابط بلا نص أو وصف",
    "Accessibility: buttons with no text or label": "سهولة الوصول: أزرار بلا نص أو وصف",
    "Accessibility: form fields without a label": "سهولة الوصول: حقول نماذج بلا عنوان",
    "Accessibility: embedded frames without a title": "سهولة الوصول: إطارات مضمّنة بلا عنوان",
    "Accessibility: heading levels skipped": "سهولة الوصول: قفز في مستويات العناوين",
    'Accessibility: vague link text ("click here", "more")': "سهولة الوصول: نص رابط غير واضح («اضغط هنا»، «المزيد»)",
    "Accessibility: the same id used twice": "سهولة الوصول: المعرّف نفسه مستخدم مرتين",
    "Speed: page heavier than 1.5 MB": "السرعة: صفحة أثقل من 1.5 ميغابايت",
    "Speed: images larger than 400 KB": "السرعة: صور أكبر من 400 كيلوبايت",
    "Speed: images without width and height (the page jumps while loading)": "السرعة: صور بلا عرض وارتفاع (تقفز الصفحة أثناء التحميل)",
    "Speed: scripts that delay the first paint": "السرعة: سكربتات تؤخر ظهور الصفحة",
    "Hide from the site on (optional)": "إخفاء من الموقع في (اختياري)", "Hidden from the site on": "يُخفى من الموقع في",
    "For offers, events and announcements: the record disappears from the site at this time by itself.":
        "للعروض والفعاليات والإعلانات: يختفي السجل من الموقع وحده في هذا الوقت.",
    "Quick search": "بحث سريع", "Search pages, records, contacts, deals…": "البحث في الصفحات والسجلات وجهات الاتصال والصفقات…",
    "↑ ↓ to move, Enter to open, Esc to close": "↑ ↓ للتنقل، Enter للفتح، Esc للإغلاق", "Dashboard": "لوحة التحكم",
    "Pages": "الصفحات", "Contacts": "جهات الاتصال", "Organisations": "المؤسسات", "Deals": "الصفقات",
    # updates
    "Updates": "التحديثات", "Check for updates": "البحث عن تحديثات", "Installed version": "النسخة المثبّتة",
    "Installed": "ثُبّتت", "Not recorded yet. It is recorded after the first update.": "لم تُسجّل بعد، وتُسجّل بعد أول تحديث.",
    "Latest in the repository": "أحدث نسخة في المستودع", "Update now": "التحديث الآن", "Press Check for updates.": "اضغطوا «البحث عن تحديثات».",
    "Update Technting CMS now? A full backup is taken first, and the site goes back to the current version by itself if anything fails.":
        "تحديث Technting CMS الآن؟ تُؤخذ نسخة احتياطية كاملة أولاً، ويعود الموقع إلى النسخة الحالية وحده إذا فشل أي شيء.",
    "Last update": "آخر تحديث", "What is new": "ما الجديد", "Change notes are written by the developers in English.": "ملاحظات التغيير مكتوبة بالإنجليزية من فريق التطوير.",
    "The server reads the private repository with a read-only key. Before every update it backs up the database, the uploaded files and the code; if a step fails, the previous version comes back by itself.":
        "يقرأ الخادم المستودع الخاص بمفتاح للقراءة فقط. وقبل كل تحديث يأخذ نسخة احتياطية من قاعدة البيانات والملفات المرفوعة والكود، وإذا فشلت أي خطوة تعود النسخة السابقة وحدها.",
    "Download the update": "تنزيل التحديث", "Full backup": "نسخة احتياطية كاملة", "Install the new files": "تثبيت الملفات الجديدة",
    "Update packages": "تحديث الحزم", "Update the database": "تحديث قاعدة البيانات", "Prepare styles and scripts": "تجهيز ملفات التصميم والسكربتات",
    "Restart without downtime": "إعادة التشغيل دون توقف", "Check the dashboard answers": "التأكد من أن لوحة التحكم تعمل", "Publish the site": "نشر الموقع",
    "Running…": "جارٍ التنفيذ…", "Updated": "تم التحديث", "Failed": "فشل",
    "The previous version was put back. Nothing was lost.": "أُعيدت النسخة السابقة، ولم يضع شيء.",
    "The update stopped before changing anything.": "توقف التحديث قبل أن يغيّر أي شيء.",
    "Could not reach the repository:": "تعذّر الوصول إلى المستودع:",
    "Could not reach the update server:": "تعذّر الوصول إلى خادم التحديثات:", "Latest release": "أحدث إصدار",
    # licence (cms/licence.py)
    "Licence": "الرخصة", "Open Settings, Licence": "افتحوا الإعدادات ثم الرخصة", "Check now": "تحقق الآن",
    "Technting CMS licence": "رخصة Technting CMS", "Active": "فعّالة", "Updates are off": "التحديثات متوقفة",
    "Installation id": "معرّف التثبيت", "Last check": "آخر تحقق", "Change the licence key": "تغيير مفتاح الرخصة",
    "Add the licence key": "إضافة مفتاح الرخصة", "Save the key": "حفظ المفتاح",
    "The licence key is saved and active.": "حُفظ مفتاح الرخصة وهو فعّال.",
    "Without a valid licence the site keeps working; only Settings, Updates is off.":
        "من دون رخصة صالحة يبقى الموقع يعمل، وتتوقف فقط صفحة الإعدادات ثم التحديثات.",
    "The licence server could not be reached at the last check. Everything keeps working; days left before updates stop:":
        "تعذّر الوصول إلى خادم الرخص في آخر تحقق. كل شيء يعمل كالمعتاد، والأيام المتبقية قبل توقف التحديثات:",
    "Add your Technting CMS licence key. Updates are off until then.": "أضيفوا مفتاح رخصة Technting CMS. التحديثات متوقفة حتى ذلك الحين.",
    "This licence key already runs on another website. Fill in the download form on technting.com again to get a key for this website. Updates are off until then.":
        "مفتاح الرخصة هذا يعمل على موقع آخر. املؤوا نموذج التنزيل في technting.com مرة أخرى لتحصلوا على مفتاح لهذا الموقع. التحديثات متوقفة حتى ذلك الحين.",
    "This licence key was cancelled. Fill in the download form on technting.com again to get a new key. Updates are off until then.":
        "أُلغي مفتاح الرخصة هذا. املؤوا نموذج التنزيل في technting.com مرة أخرى لتحصلوا على مفتاح جديد. التحديثات متوقفة حتى ذلك الحين.",
    "This licence key is not valid. Paste the key from your download e-mail as it is. Updates are off until then.":
        "مفتاح الرخصة هذا غير صالح. الصقوا المفتاح من رسالة التنزيل كما هو. التحديثات متوقفة حتى ذلك الحين.",
    "The licence server could not be reached for 30 days, so the licence could not be checked. Check that this server can reach licenses.technting.com. Updates are off until then.":
        "تعذّر الوصول إلى خادم الرخص مدة 30 يوماً، فلم يمكن التحقق من الرخصة. تأكدوا أن هذا الخادم يصل إلى licenses.technting.com. التحديثات متوقفة حتى ذلك الحين.",
    "Updates are the published Technting CMS releases, downloaded over HTTPS from technting.com. Before every update the server backs up the database, the uploaded files and the code; if a step fails, the previous version comes back by itself.":
        "التحديثات هي إصدارات Technting CMS المنشورة، وتُنزَّل عبر HTTPS من technting.com. وقبل كل تحديث يأخذ الخادم نسخة احتياطية من قاعدة البيانات والملفات المرفوعة والكود، وإذا فشلت أي خطوة تعود النسخة السابقة وحدها.",
    "Update started. This page shows each step; it takes one to three minutes.": "بدأ التحديث. تعرض هذه الصفحة كل خطوة، ويستغرق من دقيقة إلى ثلاث دقائق.",
    # bulk actions
    "Bulk action": "إجراء جماعي", "With the selected…": "على المحدد…", "Show on the site": "إظهار على الموقع", "Hide from the site": "إخفاء من الموقع",
    "Apply": "تطبيق", "Select all": "تحديد الكل", "Apply to the selected records?": "تطبيق على السجلات المحددة؟",
    "Delete the selected records in every language? This cannot be undone.": "حذف السجلات المحددة بكل اللغات؟ لا يمكن التراجع عن ذلك.",
    "Choose an action and at least one record.": "اختاروا إجراءً وسجلاً واحداً على الأقل.", "Done:": "تم:",
    # security
    "Security": "الأمان", "Check the site again": "فحص الموقع من جديد", "Summary": "الملخص",
    "Sign-ins, last 30 days": "تسجيلات الدخول خلال آخر 30 يوماً", "successful": "ناجحة", "failed": "فاشلة",
    "Failed attempts by address": "المحاولات الفاشلة حسب العنوان", "Failed attempts by user name": "المحاولات الفاشلة حسب اسم المستخدم",
    "After 5 wrong attempts an address is blocked for 15 minutes. Full details are in": "بعد 5 محاولات خاطئة يُحظر العنوان لمدة 15 دقيقة. التفاصيل الكاملة في",
    "Accounts": "الحسابات", "Two-step verification required for everyone": "التحقق بخطوتين مطلوب للجميع",
    "Two-step verification optional": "التحقق بخطوتين اختياري", "User": "المستخدم", "Role": "الدور", "Last sign-in": "آخر تسجيل دخول",
    "Admin": "مدير", "Editor": "محرر", "Author": "كاتب", "On": "مفعّل", "Off": "متوقف",
    "Each person turns it on from My account → Two-step verification. Then require it for everyone in Settings.":
        "يفعّله كل شخص من «حسابي» ← «التحقق بخطوتين». بعدها اجعلوه مطلوباً للجميع من «الإعدادات».",
    "Certificate": "الشهادة", "Could not check the site": "تعذّر فحص الموقع",
    "Security headers are added in the web server (nginx) or Cloudflare by a developer. Last check":
        "يضيف المطوّر ترويسات الأمان في خادم الويب (nginx) أو في Cloudflare. آخر فحص",
    "Last backup": "آخر نسخة احتياطية", "No problems found": "لا توجد مشكلات",
    "Administrators without two-step verification": "مديرون بلا تحقق بخطوتين", "Users without two-step verification": "مستخدمون بلا تحقق بخطوتين",
    "Two-step verification is not required for everyone (Settings)": "التحقق بخطوتين غير مطلوب للجميع (الإعدادات)",
    "Accounts not used for more than 90 days: consider turning them off": "حسابات لم تُستخدم منذ أكثر من 90 يوماً: فكّروا في إيقافها",
    "Many failed sign-ins in the last 30 days": "محاولات دخول فاشلة كثيرة خلال آخر 30 يوماً", "Security headers missing": "ترويسات أمان ناقصة",
    "Certificate expires soon": "الشهادة تنتهي قريباً", "No backup found": "لا توجد نسخة احتياطية",
    "The last backup is more than two days old": "آخر نسخة احتياطية أقدم من يومين", "Debug mode is on": "وضع التصحيح مفعّل",
    "Browsers always use HTTPS for the site, even if someone types http://.": "تستخدم المتصفحات HTTPS دائماً مع الموقع، حتى لو كتب أحدهم http://.",
    "Stops browsers from guessing file types, which blocks some attacks.": "يمنع المتصفح من تخمين نوع الملف، وهذا يصد بعض الهجمات.",
    "Stops other sites from showing our pages inside a frame (clickjacking).": "يمنع المواقع الأخرى من عرض صفحاتنا داخل إطار (خداع النقر).",
    "Limits how much of our addresses is shared with other sites.": "يحدّ مما يُشارك من روابطنا مع المواقع الأخرى.",
    "Lists the places scripts may load from; the strongest defence against injected scripts.": "يحدد الأماكن التي يُسمح بتحميل السكربتات منها، وهو أقوى حماية من السكربتات المحقونة.",
    "Turns off browser features the site does not use, such as the camera.": "يوقف ميزات المتصفح التي لا يستخدمها الموقع، مثل الكاميرا.",
    "Unused files": "ملفات غير مستخدمة",
    "These files are not used on any page, record, menu or setting. Check before deleting: a file may be linked from outside the site, for example in an email.":
        "هذه الملفات غير مستخدمة في أي صفحة أو سجل أو قائمة أو إعداد. تأكدوا قبل الحذف، فقد يكون الملف مرتبطاً من خارج الموقع، مثلاً في رسالة بريد.",
    "This file is in use. Remove it from those pages first, or use Replace file.": "هذا الملف مستخدم. أزيلوه من تلك الصفحات أولاً، أو استخدموا «استبدال الملف».",
    "Choose a file.": "اختاروا ملفاً.",
    "Videos can be up to 95 MB and other files up to 20 MB. For longer videos, use YouTube or Vimeo.": "حجم الفيديو حتى 95 ميغابايت، وباقي الملفات حتى 20 ميغابايت. للفيديوهات الأطول استخدموا YouTube أو Vimeo.",
    "The image could not be read.": "تعذّرت قراءة الصورة.",
    "Replace an image with an image, a video with a video and a PDF with a PDF.": "استبدلوا الصورة بصورة، والفيديو بفيديو، وملف PDF بملف PDF.",
    "Only JPEG, PNG, WebP, GIF, PDF, MP4 and WebM files can be uploaded.": "يمكن رفع ملفات JPEG وPNG وWebP وGIF وPDF وMP4 وWebM فقط.",
    "Videos can be up to 95 MB and other files up to 20 MB.": "حجم الفيديو حتى 95 ميغابايت، وباقي الملفات حتى 20 ميغابايت.",
    "Duplicate": "إنشاء نسخة", "Compare": "مقارنة", "copy": "نسخة",
    "Make a draft copy of this page?": "إنشاء نسخة مسودة من هذه الصفحة؟", "Make a draft copy of this record?": "إنشاء نسخة مسودة من هذا السجل؟",
    "Copy created as a draft. Change its title and address before publishing.": "أُنشئت نسخة كمسودة. غيّروا عنوانها ورابطها قبل النشر.",
    "The address changed, so visitors and search engines are sent from the old address to the new one:":
        "تغيّر الرابط، لذلك يُحوَّل الزوار ومحركات البحث من الرابط القديم إلى الجديد:",
    "Compare revision": "مقارنة نسخة سابقة", "Back to the editor": "العودة إلى المحرر", "Restore this revision": "استرجاع هذه النسخة",
    "Revision from": "نسخة من", "Removed since this revision": "حُذف منذ هذه النسخة", "Added since this revision": "أُضيف منذ هذه النسخة",
    "Added": "أُضيف", "Removed": "حُذف", "Changed": "تغيّر",
    "No differences: this revision matches the current version.": "لا فرق: هذه النسخة مطابقة للنسخة الحالية.",
    "This item no longer exists.": "هذا العنصر لم يعد موجوداً.",
}.items():
    AR.setdefault(_k, _v)

# Technting Shield strings; setdefault keeps any wording already chosen for the same English text
for _k, _v in {
    "Technting Shield": "Technting Shield", "Overview": "نظرة عامة", "Live log": "السجل المباشر", "Blocked addresses": "العناوين المحظورة",
    "Threat lists": "قوائم التهديدات", "Scans": "الفحوصات", "Sessions": "الجلسات",
    "Protecting: attacks are blocked": "الحماية مفعّلة: تُحظر الهجمات", "Learning mode: attacks are only logged": "وضع التعلّم: تُسجَّل الهجمات فقط",
    "Technting Shield is turned off. Turn it on in Plugins to protect the dashboard with a firewall, threat lists, sign-in protection and daily security checks.":
        "Technting Shield متوقف. فعّلوه من «الإضافات» لحماية لوحة التحكم بجدار حماية وقوائم تهديدات وحماية لتسجيل الدخول وفحوصات أمان يومية.",
    "Blocked today": "محظور اليوم", "Blocked in 7 days": "محظور خلال 7 أيام", "Logged only, 7 days": "مسجَّل فقط، 7 أيام",
    "Wrong passwords, 7 days": "كلمات مرور خاطئة، 7 أيام", "Needs attention": "يحتاج إلى انتباه", "What was stopped, 7 days": "ما تم إيقافه، 7 أيام",
    "Nothing yet.": "لا شيء بعد.", "Most active addresses, 7 days": "أكثر العناوين نشاطاً، 7 أيام", "Protection status": "حالة الحماية",
    "entries": "عنصر", "not downloaded yet": "لم تُنزَّل بعد", "Package check": "فحص الحزم", "problems": "مشكلة", "not run yet": "لم يُشغَّل بعد",
    "File check": "فحص الملفات", "files": "ملف", "Certificate watch": "مراقبة الشهادات", "certificates": "شهادة",
    "Blocks at Cloudflare's edge": "الحظر على شبكة Cloudflare", "Blocked addresses now": "العناوين المحظورة الآن",
    "Lists refresh by themselves every day, and the checks run in the background. Settings are in Plugins → Technting Shield.":
        "تتحدّث القوائم وحدها كل يوم، وتعمل الفحوصات في الخلفية. الإعدادات في «الإضافات» ← Technting Shield.",
    "Type": "النوع", "Firewall": "جدار الحماية", "Sign-ins": "تسجيلات الدخول", "Result": "النتيجة", "Blocked": "تم الحظر",
    "Logged": "مسجَّل فقط", "Alert": "تنبيه", "Importance": "الأهمية", "High": "عالية", "Medium": "متوسطة", "Low": "منخفضة", "Info": "معلومة",
    "Filter": "تصفية", "Update live": "تحديث مباشر", "Time": "الوقت", "Event": "الحدث", "Request": "الطلب", "Details": "التفاصيل",
    "Nothing logged yet.": "لم يُسجَّل شيء بعد.",
    "Repeats of the same event from the same address within 5 minutes are counted on one line (×). The log keeps 90 days.":
        "يُحسب تكرار الحدث نفسه من العنوان نفسه خلال 5 دقائق في سطر واحد (×). يحتفظ السجل بآخر 90 يوماً.",
    "Block an address": "حظر عنوان", "Address or network": "العنوان أو الشبكة", "Reason": "السبب", "For how long": "المدة",
    "1 hour": "ساعة", "1 day": "يوم", "1 week": "أسبوع", "30 days": "30 يوماً", "Until removed": "حتى الإزالة", "Block": "حظر",
    "Never blocked": "لا يُحظر أبداً", "No addresses on the allow list.": "لا توجد عناوين في قائمة السماح.",
    "Add your office address in Plugins → Technting Shield → Never block these addresses, so a mistake can never lock the team out.":
        "أضيفوا عنوان المكتب في «الإضافات» ← Technting Shield ← «لا تحظر هذه العناوين أبداً»، حتى لا يُحظر الفريق بالخطأ.",
    "Cloudflare copies our blocks of single addresses to its edge, so they also protect the public website.":
        "تنسخ Cloudflare حظر العناوين المفردة إلى شبكتها، فيحمي الموقع العام أيضاً.",
    "Test the connection and sync now": "اختبار الاتصال والمزامنة الآن", "Blocked now": "محظور الآن", "By": "بواسطة", "Until": "حتى",
    "Stopped": "مرات الإيقاف", "Unblock": "إلغاء الحظر", "No addresses are blocked.": "لا توجد عناوين محظورة.",
    "Update all now": "تحديث الكل الآن", "List": "القائمة", "Entries": "العناصر", "Updated": "آخر تحديث", "Every": "كل", "Use": "الاستخدام",
    "out of date": "قديمة", "Log (block if chosen)": "تسجيل (وحظر إذا اخترتم)", "Trust": "موثوقة",
    "If a download fails, the last good copy stays in use. Private and Cloudflare addresses are never blocked, whatever a list says.":
        "إذا فشل التنزيل تبقى آخر نسخة سليمة مستخدمة. لا تُحظر العناوين الخاصة وعناوين Cloudflare أبداً، مهما قالت القوائم.",
    "Check an address": "فحص عنوان", "On threat lists": "في قوائم التهديدات", "Yes": "نعم", "No": "لا", "On the allow list": "في قائمة السماح",
    "Cloudflare server": "خادم Cloudflare", "Private address": "عنوان خاص", "reports": "بلاغ", "Lines in our log": "أسطر في سجلنا",
    "Package check (OSV.dev)": "فحص الحزم (OSV.dev)", "No known problems": "لا توجد مشكلات معروفة", "packages checked, every day": "حزمة مفحوصة، كل يوم",
    "Package": "الحزمة", "Problem": "المشكلة", "Fixed in": "أُصلحت في", "Not run yet.": "لم يُشغَّل بعد.",
    "A developer updates the package to the fixed version, tests and deploys. Data: OSV.dev (Google's open vulnerability database).":
        "يحدّث المطوّر الحزمة إلى النسخة المُصلَحة، ثم يختبر وينشر. البيانات من OSV.dev (قاعدة الثغرات المفتوحة من Google).",
    "Accept the current files": "اعتماد الملفات الحالية",
    "Accept the files as they are now as the reference? Do this only right after a deployment you know about.":
        "اعتماد الملفات كما هي الآن مرجعاً؟ افعلوا ذلك فقط بعد تحديث تعرفون به.",
    "Compared with": "مقارنة مع", "the deployed commit": "النسخة المنشورة من الكود", "the Git commit": "آخر نسخة في Git", "the version installed by Updates": "النسخة التي ثبّتتها صفحة التحديثات", "the saved reference": "المرجع المحفوظ",
    "New files": "ملفات جديدة", "Missing": "مفقودة", "All files match": "كل الملفات مطابقة",
    "Unexpected files in the public website folder": "ملفات غير متوقعة في مجلد الموقع العام",
    "Runs every hour. A change that was not a deployment can mean someone got into the server.":
        "يعمل كل ساعة. أي تغيير لم يأتِ من تحديث مقصود قد يعني أن أحداً دخل إلى الخادم.",
    "Names": "الأسماء", "Issued by": "الجهة المُصدِرة", "Valid": "الصلاحية",
    "Every certificate for our domain is published in public logs. Technting Shield checks them twice a day and alerts you when a certificate appears for a new name or from a new authority. Data: crt.sh (Sectigo), Cert Spotter.":
        "تُنشر كل شهادة لنطاقنا في سجلات عامة. يفحصها Technting Shield مرتين في اليوم وينبّهكم عند ظهور شهادة لاسم جديد أو من جهة جديدة. البيانات من crt.sh (Sectigo) وCert Spotter.",
    "Signed-in sessions": "الجلسات المفتوحة", "Sign out all my other sessions": "تسجيل خروجي من كل الجلسات الأخرى", "Browser": "المتصفح",
    "Signed in": "وقت الدخول", "This session": "هذه الجلسة", "Known devices": "الأجهزة المعروفة", "Country": "الدولة",
    "First seen": "أول ظهور", "Last seen": "آخر ظهور",
    "A sign-in from a device or country not seen before is logged, and emailed to administrators who turned on security alerts in My account.":
        "يُسجَّل الدخول من جهاز أو دولة جديدة، ويُرسل بالبريد للمديرين الذين فعّلوا تنبيهات الأمان من «حسابي».",
    "Security alerts by email": "تنبيهات الأمان بالبريد",
    "Technting Shield emails you at once when someone signs in to your account from a new device or country, and when it finds a serious problem: a new certificate for our domain, changed code files, a package that needs a security update. Sent to":
        "يرسل لكم Technting Shield رسالة فوراً عند تسجيل الدخول إلى حسابكم من جهاز أو دولة جديدة، وعند وجود مشكلة خطيرة: شهادة جديدة لنطاقنا، أو ملفات كود تغيّرت، أو حزمة تحتاج إلى تحديث أمني. تُرسل إلى",
    "Send me security alerts": "أرسلوا لي تنبيهات الأمان", "Other sessions": "الجلسات الأخرى",
    "Signed in on a computer you no longer use, or lost a phone? Sign out everywhere except here.":
        "سجّلتم الدخول من جهاز لم تعودوا تستخدمونه، أو فقدتم هاتفاً؟ سجّلوا الخروج من كل مكان ما عدا هنا.",
    "Technting Shield adds a firewall, lockouts and a live log:": "يضيف Technting Shield جدار حماية وحظراً بعد المحاولات الخاطئة وسجلاً مباشراً:",
    "For a firewall, threat lists and sign-in alerts, turn on Technting Shield in": "لتفعيل جدار الحماية وقوائم التهديدات وتنبيهات الدخول، فعّلوا Technting Shield من",
    # messages
    "Blocked.": "تم الحظر.", "Unblocked.": "أُلغي الحظر.", "Signed out.": "تم تسجيل الخروج.", "Done.": "تم.",
    "Other sessions signed out:": "عدد الجلسات الأخرى التي أُغلقت:", "The current files are now the reference.": "أصبحت الملفات الحالية هي المرجع.",
    "Enter an address such as 203.0.113.7 or a network such as 203.0.113.0/24.": "أدخلوا عنواناً مثل 203.0.113.7 أو شبكة مثل 203.0.113.0/24.",
    "Enter an address such as 203.0.113.7.": "أدخلوا عنواناً مثل 203.0.113.7.",
    "That network is too large to block safely.": "هذه الشبكة أكبر من أن تُحظر بأمان.",
    "That address is on the allow list, or it is your own address.": "هذا العنوان في قائمة السماح، أو هو عنوانكم أنتم.",
    "Removed here, but Cloudflare did not confirm:": "أُزيل هنا، لكن Cloudflare لم تؤكد الإزالة:",
    "That is a Cloudflare server: blocking it would block many visitors.": "هذا خادم من Cloudflare، وحظره يحظر زواراً كثيرين.",
    "Cloudflare connection works:": "الاتصال بـ Cloudflare يعمل:", "Cloudflare connection failed:": "فشل الاتصال بـ Cloudflare:",
    # log events
    "On the Spamhaus DROP list": "في قائمة Spamhaus DROP", "On the FireHOL level 1 list": "في قائمة FireHOL level 1",
    "Tor exit node": "مخرج من شبكة Tor", "Blocked by an administrator": "حظره مدير", "Blocked automatically": "حُظر تلقائياً",
    "Country not allowed": "دولة غير مسموحة", "Country not allowed for the dashboard": "دولة غير مسموحة للوحة التحكم",
    "Probe for a known weak spot": "بحث عن ثغرة معروفة", "Attack tool": "أداة هجوم", "SQL injection attempt": "محاولة حقن SQL",
    "Script injection attempt (XSS)": "محاولة حقن سكربت (XSS)", "Attempt to read server files": "محاولة قراءة ملفات الخادم",
    "Attempt to run commands": "محاولة تشغيل أوامر", "Too many requests": "طلبات كثيرة جداً",
    "Request did not come through Cloudflare": "طلب لم يمرّ عبر Cloudflare", "Wrong password": "كلمة مرور خاطئة",
    "Sign-in with a blocked user name": "محاولة دخول باسم مستخدم محظور", "Locked out after wrong passwords": "حظر بعد كلمات مرور خاطئة",
    "Sign-in from a new device": "دخول من جهاز جديد", "Sign-in from a new country": "دخول من دولة جديدة",
    "Many wrong passwords for one account": "كلمات مرور خاطئة كثيرة لحساب واحد", "Password found in a data breach": "كلمة مرور موجودة في تسريب بيانات",
    "Address with a bad reputation (AbuseIPDB)": "عنوان سمعته سيئة (AbuseIPDB)", "Code files changed": "تغيّرت ملفات الكود",
    "Unexpected file in the public website folder": "ملف غير متوقع في مجلد الموقع العام", "Vulnerable package": "حزمة فيها ثغرة",
    "New certificate for our domain": "شهادة جديدة لنطاقنا", "A threat list could not be updated": "تعذّر تحديث قائمة تهديدات",
    "Other sessions signed out": "أُغلقت الجلسات الأخرى",
    # findings and lists
    "Technting Shield is in learning mode: attacks are logged, not blocked": "Technting Shield في وضع التعلّم: تُسجَّل الهجمات ولا تُحظر",
    "A threat list is out of date": "قائمة تهديدات قديمة", "Packages with serious security problems": "حزم فيها مشكلات أمنية خطيرة",
    "Packages with known security problems": "حزم فيها مشكلات أمنية معروفة", "Code files differ from the committed version": "ملفات الكود تختلف عن النسخة المعتمدة",
    "New certificates for our domain this week": "شهادات جديدة لنطاقنا هذا الأسبوع",
    "Accounts using a password found in data breaches": "حسابات تستخدم كلمة مرور موجودة في تسريبات بيانات",
    "Technting Shield: requests blocked this week": "Technting Shield: الطلبات المحظورة هذا الأسبوع",
    "Networks taken over by spammers and criminals (Spamhaus Don't Route Or Peer).": "شبكات يسيطر عليها مرسلو البريد المزعج والمجرمون (Spamhaus Don't Route Or Peer).",
    "Addresses attacking right now (DShield, abuse.ch, Spamhaus and others), with few false alarms.":
        "عناوين تهاجم الآن (من DShield وabuse.ch وSpamhaus وغيرها)، وأخطاؤها قليلة.",
    "Addresses of the Tor network's exits. Logged by default; blocked only if you choose so.":
        "عناوين مخارج شبكة Tor. تُسجَّل فقط، ولا تُحظر إلا إذا اخترتم ذلك.",
    "Tor exit nodes": "مخارج شبكة Tor", "Cloudflare addresses": "عناوين Cloudflare",
    "Cloudflare's own servers. Only requests from them may name the visitor's address.":
        "خوادم Cloudflare نفسها. فقط الطلبات القادمة منها يُعتمد ما تذكره عن عنوان الزائر.",
}.items():
    AR.setdefault(_k, _v)

# Technting Shield 1.1 strings (domain, lookalikes, public files, media, Turnstile)
for _k, _v in {
    "Domain and email security": "أمان النطاق والبريد", "Lookalike domains": "نطاقات مشابهة لنطاقنا", "Public website files": "ملفات الموقع العام",
    "Media library check": "فحص مكتبة الوسائط", "Accept the unknown files": "اعتماد الملفات غير المعروفة",
    "Accept the unknown files as known? Do this only after a developer checked them.": "اعتماد الملفات غير المعروفة على أنها معروفة؟ افعلوا ذلك فقط بعد أن يفحصها مطوّر.",
    "All files match what the CMS published": "كل الملفات مطابقة لما نشره نظام إدارة المحتوى", "Changed outside the CMS": "تغيّرت من خارج نظام إدارة المحتوى",
    "Deleted": "محذوفة", "New files the CMS did not make": "ملفات جديدة لم ينشئها نظام إدارة المحتوى",
    "files published by the CMS": "ملفاً نشرها نظام إدارة المحتوى", "other files": "ملفات أخرى",
    "Every hour Technting Shield compares each public file with the fingerprint the CMS saved when it published it. A difference means the website was changed on the server; publishing again puts it back.":
        "يقارن Technting Shield كل ساعة كل ملف في الموقع العام بالبصمة التي حفظها النظام عند نشره. أي اختلاف يعني أن الموقع تغيّر على الخادم، وإعادة النشر ترجعه كما كان.",
    "No suspicious files": "لا توجد ملفات مشبوهة",
    "Checks that every uploaded file really is an image, video or PDF and hides no code. Runs every 6 hours; only new files are read.":
        "يتأكد أن كل ملف مرفوع هو فعلاً صورة أو فيديو أو PDF ولا يخفي كوداً. يعمل كل 6 ساعات ويقرأ الملفات الجديدة فقط.",
    "Not checked (DNS did not answer)": "لم يُفحص (لم يردّ نظام أسماء النطاقات)",
    "Checked every 6 hours. A change of name servers or mail servers is emailed at once: it is the usual sign of a stolen domain. SPF and DMARC stop others from sending email in our name.":
        "يُفحص كل 6 ساعات. أي تغيير في خوادم الأسماء أو خوادم البريد يصلكم بالبريد فوراً، لأنه العلامة المعتادة على سرقة النطاق. سجلّا SPF وDMARC يمنعان الآخرين من إرسال بريد باسمنا.",
    "names checked, every day": "اسماً تُفحص كل يوم", "certificate search did not answer": "بحث الشهادات لم يردّ",
    "Found by": "طريقة الاكتشاف", "No lookalike domains are registered.": "لا توجد نطاقات مشابهة مسجّلة.",
    "Names one typo away from ours, other endings (.net, .co, .sa ...) and names with words like login or secure. One that can receive email can be used for fake messages to clients. Our own domains are set in Plugins → Technting Shield.":
        "أسماء تختلف عن اسمنا بحرف واحد، أو بنهاية أخرى (‎.net‎ و‎.co‎ و‎.sa‎ وغيرها)، أو تضيف كلمات مثل login وsecure. الاسم الذي يستقبل بريداً يمكن استخدامه لرسائل مزيفة إلى العملاء. نطاقاتنا الأخرى تُضاف من «الإضافات» ← Technting Shield.",
    "SPF is set": "سجل SPF موجود", "DMARC is set": "سجل DMARC موجود",
    "No SPF record: anyone can send email that looks like ours": "لا يوجد سجل SPF: يستطيع أي أحد إرسال بريد يبدو أنه منا",
    "More than one SPF record: receiving servers ignore them all": "يوجد أكثر من سجل SPF، فتتجاهلها خوادم البريد كلها",
    "SPF allows every server to send our email (+all)": "سجل SPF يسمح لأي خادم بإرسال بريد باسمنا (‎+all‎)",
    "SPF does not say what to do with other servers (?all)": "سجل SPF لا يحدد ماذا يُفعل بالخوادم الأخرى (‎?all‎)",
    "No DMARC record: fake emails in our name are not rejected": "لا يوجد سجل DMARC: لا تُرفض الرسائل المزيفة باسمنا",
    "DMARC only watches (p=none): fake emails still arrive": "سجل DMARC يراقب فقط (‎p=none‎): ما زالت الرسائل المزيفة تصل",
    "DMARC has no report address (rua): you never see who sends in your name": "سجل DMARC بلا عنوان تقارير (rua): لن تعرفوا من يرسل باسمكم",
    "CAA lists the authorities that may issue our certificates": "سجل CAA يحدد الجهات المسموح لها بإصدار شهاداتنا",
    "No CAA record: any certificate authority may issue certificates for us": "لا يوجد سجل CAA: أي جهة شهادات تستطيع إصدار شهادة لنطاقنا",
    "DNSSEC is on": "DNSSEC مفعّل", "DNSSEC is off (can be turned on in Cloudflare with one click)": "DNSSEC غير مفعّل (يُفعَّل من Cloudflare بنقرة واحدة)",
    "Not behind Cloudflare: the server's real address is public": "غير محمي بـ Cloudflare: عنوان الخادم الحقيقي ظاهر للجميع",
    "Public website files changed outside the CMS": "ملفات في الموقع العام تغيّرت من خارج نظام إدارة المحتوى",
    "New files on the public website that the CMS did not make": "ملفات جديدة في الموقع العام لم ينشئها نظام إدارة المحتوى",
    "Suspicious files in the media library": "ملفات مشبوهة في مكتبة الوسائط", "Lookalike domains registered this week": "نطاقات مشابهة سُجّلت هذا الأسبوع",
    "Failed the human check (Turnstile)": "لم ينجح في فحص «هل أنت إنسان» (Turnstile)", "Domain records changed": "تغيّرت سجلات النطاق",
    "Lookalike domain registered": "سُجّل نطاق مشابه", "Suspicious file in the media library": "ملف مشبوه في مكتبة الوسائط",
    "Public website file changed outside the CMS": "ملف في الموقع العام تغيّر من خارج نظام إدارة المحتوى", "New file on the public website": "ملف جديد في الموقع العام",
    "script or page file in the media folder": "ملف سكربت أو صفحة في مجلد الوسائط", "file type the media library does not accept": "نوع ملف لا تقبله مكتبة الوسائط",
    "content does not match the file type": "محتوى الملف لا يطابق نوعه", "hidden code inside the file": "كود مخفي داخل الملف",
    "PDF that runs scripts or carries attachments": "ملف PDF يشغّل سكربتات أو يحمل مرفقات",
    "Please confirm that you are not a robot, then sign in again.": "أكّدوا أنكم لستم برنامجاً آلياً، ثم سجّلوا الدخول مرة أخرى.",
    "every day": "كل يوم",
}.items():
    AR.setdefault(_k, _v)

# social profiles, phone and WhatsApp; campaigns in Stats
for _k, _v in {
    "Social profiles and phone": "حسابات التواصل الاجتماعي والهاتف", "Social profiles": "حسابات التواصل الاجتماعي",
    "Profile addresses for the footer icons and search engines, and the phone and WhatsApp number shown on the site.":
        "روابط الحسابات لأيقونات أسفل الموقع ولمحركات البحث، ورقم الهاتف وواتساب الظاهر على الموقع.",
    "One account per platform. The footer of English and Arabic pages shows an icon for each profile that is on and has an address, and search engines get every profile that is on.":
        "حساب واحد لكل منصة. يعرض أسفل الصفحات الإنجليزية والعربية أيقونة لكل حساب مفعّل له رابط، وتحصل محركات البحث على كل الحسابات المفعّلة.",
    "Add a profile only after the account is live. To remove one, empty its address.":
        "أضيفوا الحساب بعد أن يصبح جاهزاً للزوار فقط. لحذف حساب، امسحوا رابطه.",
    "Platform": "المنصة", "Profile address": "رابط الحساب", "Name (for Other)": "الاسم (لخيار «أخرى»)", "In footer": "أسفل الموقع",
    "WhatsApp channel": "قناة واتساب", "Other": "أخرى",
    "Need more rows? Save, and empty rows are added again.": "تحتاجون صفوفاً أكثر؟ احفظوا، وستُضاف صفوف فارغة من جديد.",
    "Phone and WhatsApp": "الهاتف وواتساب",
    "Shown in the footer, on the contact page and to search engines. Write it with the country code, as on the social profiles.":
        "يظهر أسفل الموقع وفي صفحة التواصل ولمحركات البحث. اكتبوه مع رمز الدولة، كما في حسابات التواصل الاجتماعي.",
    "The WhatsApp link opens a chat with this number. Leave empty to hide it.": "رابط واتساب يفتح محادثة مع هذا الرقم. اتركوه فارغاً لإخفائه.",
    "Links page": "صفحة الروابط", "A short page of main links for social media bios:": "صفحة قصيرة بأهم الروابط للتعريف في حسابات التواصل الاجتماعي:",
    "Featured link": "رابط مميّز",
    "Leave empty to hide this line on the links page.": "اتركوه فارغاً لإخفاء هذا السطر في صفحة الروابط.",
    "Sent to search engines (sameAs)": "ما يُرسل إلى محركات البحث (sameAs)",
    "Nothing was saved. Check these values (profile addresses must start with https://):": "لم يُحفظ شيء. راجعوا هذه القيم (روابط الحسابات تبدأ بـ https://):",
    "Visits from links tagged with utm_campaign, utm_content, utm_source and utm_medium.": "الزيارات القادمة من روابط تحمل utm_campaign وutm_content وutm_source وutm_medium.",
    "Campaign": "الحملة", "Medium": "الوسيلة", "Visits": "الزيارات", "Show": "عرض", "Clear": "مسح",
    "No visits from tagged links in this period yet.": "لا توجد بعد زيارات من روابط الحملات في هذه الفترة.", "Total": "المجموع",
    "Source": "المصدر",
}.items():
    AR.setdefault(_k, _v)

JS_AR = {
    "has this open right now. If you both save, the later save replaces the earlier one.": "يفتح هذا العنصر الآن. إذا حفظتم كلاكما، يحلّ الحفظ الأخير محل الأول.",
    "Edit anyway": "التعديل على أي حال",
    "Address": "الرابط", "Size": "الحجم", "Uploaded": "تاريخ الرفع", "Title": "العنوان", "Alternative text": "النص البديل",
    "English": "الإنجليزية", "Arabic": "العربية", "Save": "حفظ", "Delete": "حذف", "Used in": "مستخدم في",
    "Not used anywhere on the site.": "غير مستخدم في أي مكان على الموقع.", "Replace file": "استبدال الملف",
    "Saved. Publish the site to update pages that use it.": "تم الحفظ. انشروا الموقع لتحديث الصفحات التي تستخدمه.",
    "Replace this file everywhere it is used and publish the site?": "استبدال هذا الملف في كل مكان يُستخدم فيه ونشر الموقع؟",
    "Replaced and published.": "تم الاستبدال والنشر.", "Files uploaded:": "الملفات المرفوعة:", "Delete this file permanently?": "حذف هذا الملف نهائياً؟",
    "Unsaved changes from": "وُجدت في هذا المتصفح تعديلات غير محفوظة من", "were found in this browser.": ".",
    "Restore them": "استرجاعها", "Discard": "تجاهلها",
    "+ Add block": "+ إضافة قسم", "Add a block": "إضافة قسم", "Choose": "اختيار", "Remove": "إزالة", "No image": "لا توجد صورة",
    "Media library": "مكتبة الوسائط", "Search media": "البحث في الوسائط", "Use image": "استخدام الصورة", "Cancel": "إلغاء",
    "Delete this block?": "حذف هذا القسم؟", "Remove this item?": "إزالة هذا العنصر؟", "Uploading…": "جارٍ الرفع…", "Uploaded.": "تم الرفع.",
    "Select…": "اختاروا…", "Loading…": "جارٍ التحميل…", "(none)": "(بدون)", "Only administrators can edit custom HTML.": "تعديل HTML المخصص متاح للمديرين فقط.",
    "Move up": "تحريك للأعلى", "Move down": "تحريك للأسفل", "Duplicate": "إنشاء نسخة", "Add block below": "إضافة قسم تحته",
    "Delete block": "حذف القسم", "Drag to reorder": "اسحبوا لتغيير الترتيب", "+ Add": "+ إضافة", "item": "عنصراً",
    "characters": "حرفاً", "(search engines may cut it)": "(قد لا يظهر كاملاً في محركات البحث)",
    "Link address (https://, /page/ or mailto:)": "عنوان الرابط (‎https://‎ أو ‎/page/‎ أو ‎mailto:‎)",
    "Drop images here or ": "اسحبوا الصور إلى هنا أو ", "choose files": "اختاروا ملفات", "Template settings": "إعدادات القالب",
    "Bold": "عريض", "Italic": "مائل", "Heading": "عنوان", "Subheading": "عنوان فرعي", "Paragraph": "فقرة",
    "Bulleted list": "قائمة نقطية", "Numbered list": "قائمة مرقّمة", "Link": "رابط", "Remove formatting": "إزالة التنسيق",
    "On": "مفعّلة", "Off": "متوقفة", "missing": "مفقود", "Text": "النص", "Address": "الرابط", "Use video": "استخدام الفيديو", "No video": "لا يوجد فيديو",
    "Image": "صورة", "This block shows records from": "يعرض هذا القسم سجلات من",
    "To change names, photos or texts, edit them there:": "لتغيير الأسماء أو الصور أو النصوص، عدّلوها هناك:",
    "Hidden": "مخفي", "only": "فقط", "Show on:": "يظهر على:", "Phone": "الهاتف", "Tablet": "التابلت", "Desktop": "الكمبيوتر",
    "Hidden from the site. Click to show it": "مخفي عن زوار الموقع. اضغطوا لإظهاره",
    "Shown on the site. Click to hide it": "ظاهر لزوار الموقع. اضغطوا لإخفائه",
    "A section must show on at least one screen size. To remove it from the site, use Hide.":
        "يجب أن يظهر القسم على شاشة واحدة على الأقل. لإخفائه عن الموقع كله استخدموا زر الإخفاء.",
}

for _k, _v in {"Saved. Type a new one to replace it.": "محفوظ. اكتبوا مفتاحاً جديداً لاستبداله.",
               "Remove the saved key": "حذف المفتاح المحفوظ"}.items():
    JS_AR.setdefault(_k, _v)


def ui_lang(request):
    lang = getattr(request, "session", {}).get("ui_lang") if request is not None else None
    return lang if lang in {"en", "ar"} else "en"


def tr(text, lang):
    return AR.get(text, text) if lang == "ar" else text


# Arabic nouns change form with the number: 1 and 11+ take the singular, 2 the dual, 3-10 the plural, and
# masculine nouns take -an (رابطاً) from 11 to 99. Each entry: (one, two, few, many, many_11_to_99, zero or None).
COUNT_AR = {
    "pages checked": ("صفحة مفحوصة", "صفحتان مفحوصتان", "صفحات مفحوصة", "صفحة مفحوصة", "صفحة مفحوصة", None),
    "items to check": ("عنصر للمراجعة", "عنصران للمراجعة", "عناصر للمراجعة", "عنصر للمراجعة", "عنصراً للمراجعة", None),
    "important": ("عنصر مهم", "عنصران مهمّان", "عناصر مهمة", "عنصر مهم", "عنصراً مهماً", None),
    "broken": ("رابط معطّل", "رابطان معطّلان", "روابط معطّلة", "رابط معطّل", "رابطاً معطّلاً", "لا توجد روابط معطّلة"),
    "links": ("رابط", "رابطان", "روابط", "رابط", "رابطاً", None),
    "pages": ("صفحة", "صفحتان", "صفحات", "صفحة", "صفحة", None),
    "contacts": ("جهة اتصال", "جهتا اتصال", "جهات اتصال", "جهة اتصال", "جهة اتصال", None),
    "deals": ("صفقة", "صفقتان", "صفقات", "صفقة", "صفقة", None),
    "organisations": ("مؤسسة", "مؤسستان", "مؤسسات", "مؤسسة", "مؤسسة", None),
    "open deals": ("صفقة مفتوحة", "صفقتان مفتوحتان", "صفقات مفتوحة", "صفقة مفتوحة", "صفقة مفتوحة", None),
    "due today": ("مهمة مستحقة اليوم", "مهمتان مستحقتان اليوم", "مهام مستحقة اليوم", "مهمة مستحقة اليوم", "مهمة مستحقة اليوم", None),
    "h": ("ساعة", "ساعتان", "ساعات", "ساعة", "ساعة", None),
    "files": ("ملف", "ملفان", "ملفات", "ملف", "ملفاً", None),
    "matches": ("نتيجة", "نتيجتان", "نتائج", "نتيجة", "نتيجة", "لا توجد نتائج"),
    "records": ("سجل", "سجلان", "سجلات", "سجل", "سجلاً", None),
    "updates": ("تحديث جديد", "تحديثان جديدان", "تحديثات جديدة", "تحديث جديد", "تحديثاً جديداً", None),
    "days": ("يوم", "يومان", "أيام", "يوم", "يوماً", None),
    "hours ago": ("قبل ساعة", "قبل ساعتين", "ساعات مضت", "ساعة مضت", "ساعة مضت", "قبل أقل من ساعة"),
    "visitors": ("زائر", "زائران", "زوار", "زائر", "زائراً", "لا زوار"),
    "page views": ("مشاهدة", "مشاهدتان", "مشاهدات", "مشاهدة", "مشاهدة", None),
}
# Technting Shield counted nouns (setdefault keeps any forms already chosen)
for _k, _v in {
    "entries": ("عنصر", "عنصران", "عناصر", "عنصر", "عنصراً", None),
    "problems": ("مشكلة", "مشكلتان", "مشكلات", "مشكلة", "مشكلة", "لا توجد مشكلات"),
    "certificates": ("شهادة", "شهادتان", "شهادات", "شهادة", "شهادة", None),
    "reports": ("بلاغ", "بلاغان", "بلاغات", "بلاغ", "بلاغاً", "لا بلاغات"),
    "packages checked": ("حزمة مفحوصة", "حزمتان مفحوصتان", "حزم مفحوصة", "حزمة مفحوصة", "حزمة مفحوصة", None),
    "names checked": ("اسم مفحوص", "اسمان مفحوصان", "أسماء مفحوصة", "اسم مفحوص", "اسماً مفحوصاً", None),
    "files published by the CMS": ("ملف نشره النظام", "ملفان نشرهما النظام", "ملفات نشرها النظام", "ملف نشره النظام", "ملفاً نشره النظام", None),
    "other files": ("ملف آخر", "ملفان آخران", "ملفات أخرى", "ملف آخر", "ملفاً آخر", "لا توجد ملفات أخرى"),
}.items():
    COUNT_AR.setdefault(_k, _v)


# Technting Backup (offsite backups); setdefault keeps any wording already chosen for the same English text
for _k, _v in {
    "Offsite copies": "نسخ خارج الخادم", "Offsite settings": "إعدادات النسخ خارج الخادم", "Offsite": "خارج الخادم",
    "Offsite copy": "النسخة خارج الخادم", "restore test": "تجربة الاسترجاع", "Not set up": "غير مُعدّ", "Working": "يعمل",
    "Needs attention": "يحتاج إلى انتباه", "Failed": "فشل", "OK": "سليم", "Storage": "التخزين", "Last upload": "آخر رفع",
    "Copies in storage": "النسخ في التخزين", "Integrity check": "فحص السلامة", "Restore test": "تجربة الاسترجاع",
    "Runs once a month at night": "تعمل مرة في الشهر ليلاً", "Keep": "الاحتفاظ", "daily": "يومية", "weekly": "أسبوعية",
    "monthly": "شهرية", "Daily": "يومية", "Weekly": "أسبوعية", "Monthly": "شهرية",
    "Copy offsite now": "النسخ إلى الخارج الآن", "Run a restore test now": "تجربة الاسترجاع الآن",
    "An offsite job is running…": "عملية نسخ أو فحص قيد التشغيل…", "Set up offsite copies": "إعداد النسخ خارج الخادم",
    "Backups are kept only on this server. Turn on the Technting Backup plugin to copy them, encrypted, to Cloudflare R2, Backblaze B2 or another S3-compatible storage.":
        "النسخ الاحتياطية محفوظة على هذا الخادم فقط. فعّلوا إضافة ⁦Technting Backup⁩ لنسخها مشفّرةً إلى ⁦Cloudflare R2⁩ أو ⁦Backblaze B2⁩ أو أي تخزين آخر متوافق مع S3.",
    "Choose where the encrypted copies go and set a passphrase. It takes about 10 minutes with the guide on the next page.":
        "اختاروا مكان حفظ النسخ المشفّرة وضعوا عبارة مرور. يستغرق ذلك نحو 10 دقائق مع الشرح في الصفحة التالية.",
    "Email me when a backup or upload fails, or the newest backup is more than 36 hours old":
        "أرسلوا لي بريداً إذا فشل النسخ الاحتياطي أو الرفع، أو إذا مرّ على آخر نسخة أكثر من 36 ساعة",
    # settings page
    "The Technting Backup plugin is off, so nothing is copied yet. Turn it on in Plugins after saving these settings.":
        "إضافة ⁦Technting Backup⁩ متوقفة، لذلك لا يُنسخ شيء بعد. فعّلوها من «الإضافات» بعد حفظ هذه الإعدادات.",
    "Where the copies go": "مكان حفظ النسخ", "Other S3-compatible storage": "تخزين آخر متوافق مع S3",
    "Cloudflare account ID": "رقم حساب Cloudflare (⁦Account ID⁩)", "In Cloudflare: R2 → Overview, on the right.": "في Cloudflare: افتحوا R2 ثم Overview، وستجدونه على الجانب.",
    "Region": "المنطقة", "Part of the bucket's endpoint: s3.REGION.backblazeb2.com": "جزء من عنوان الحاوية: s3.REGION.backblazeb2.com",
    "Storage address (endpoint)": "عنوان التخزين (endpoint)", "Bucket name": "اسم الحاوية (bucket)", "Folder in the bucket": "المجلد داخل الحاوية",
    "Access key ID": "معرّف مفتاح الوصول (⁦Access Key ID⁩)", "Secret access key": "المفتاح السري (⁦Secret Access Key⁩)",
    "Leave empty to keep the saved key.": "اتركوه فارغاً للإبقاء على المفتاح المحفوظ.",
    "Encryption passphrase": "عبارة مرور التشفير", "Important:": "مهم:",
    "Backups are encrypted with this passphrase before they leave the server. Nobody can open them without it, not the storage company and not us. If you lose it, the offsite copies are lost too. Save it now in a password manager and give a second copy to another owner.":
        "تُشفَّر النسخ الاحتياطية بهذه العبارة قبل أن تخرج من الخادم، ولا يستطيع أحد فتحها من دونها، لا شركة التخزين ولا نحن. إذا ضاعت العبارة ضاعت النسخ الخارجية معها. احفظوها الآن في برنامج لحفظ كلمات المرور، وأعطوا نسخة منها لشريك آخر.",
    "A passphrase is saved. Fill these fields only to change it.": "توجد عبارة مرور محفوظة. املؤوا هذه الحقول فقط إذا أردتم تغييرها.",
    "fingerprint": "البصمة", "Passphrase (at least 12 characters)": "عبارة المرور (12 حرفاً على الأقل)", "Passphrase again": "عبارة المرور مرة أخرى",
    "Suggestion (shown once, not saved):": "اقتراح (يظهر مرة واحدة ولا يُحفظ):",
    "I saved the passphrase somewhere safe. I understand that without it the offsite copies cannot be opened.":
        "حفظتُ عبارة المرور في مكان آمن، وأعرف أن النسخ الخارجية لا تُفتح من دونها.",
    "How many copies to keep": "عدد النسخ التي نحتفظ بها",
    "The newest copy of each day, week and month is kept; older copies are deleted from the storage. The newest copy is never deleted.":
        "نحتفظ بأحدث نسخة من كل يوم وأسبوع وشهر، وتُحذف النسخ الأقدم من التخزين. أحدث نسخة لا تُحذف أبداً.",
    "Technting CMS tests the connection (write, list, read, delete a small file) before saving. Keys are stored encrypted and never shown again.":
        "يجرّب ⁦Technting CMS⁩ الاتصال قبل الحفظ (كتابة ملف صغير وعرضه وقراءته وحذفه). تُحفظ المفاتيح مشفّرة ولا تظهر مرة أخرى.",
    "Test and save": "تجربة وحفظ", "Remove offsite settings": "حذف إعدادات النسخ خارج الخادم",
    "Remove offsite settings? Copies already in the bucket stay there.": "حذف إعدادات النسخ خارج الخادم؟ النسخ الموجودة في الحاوية تبقى كما هي.",
    "Set up Cloudflare R2 (free up to 10 GB)": "إعداد ⁦Cloudflare R2⁩ (مجاني حتى 10 GB)",
    "Sign in to dash.cloudflare.com with the account that runs example.com and open R2 Object Storage. Cloudflare may ask you to add a payment card once to turn R2 on; the free tier is not charged.":
        "ادخلوا إلى dash.cloudflare.com بالحساب الذي يدير example.com وافتحوا ⁦R2 Object Storage⁩. قد يطلب Cloudflare إضافة بطاقة دفع مرة واحدة لتفعيل R2، ولا تُدفع أي رسوم ضمن الحد المجاني.",
    "Create bucket: name it technting-cms-backups, location Automatic. Leave public access off.":
        "اضغطوا ⁦Create bucket⁩ وسمّوا الحاوية ⁦technting-cms-backups⁩، والموقع Automatic. اتركوا الوصول العام (⁦Public access⁩) مغلقاً.",
    "Back on the R2 page, open Manage API tokens → Create Account API token.":
        "ارجعوا إلى صفحة R2 وافتحوا ⁦Manage API tokens⁩، ثم ⁦Create Account API token⁩.",
    "Permission: Object Read & Write. Choose “Apply to specific buckets only” and pick technting-cms-backups. This key can then touch nothing else.":
        "الصلاحية: ⁦Object Read & Write⁩. اختاروا «⁦Apply to specific buckets only⁩» ثم ⁦technting-cms-backups⁩، فلا يستطيع هذا المفتاح الوصول إلى أي شيء آخر.",
    "Press Create. Copy the Access Key ID and the Secret Access Key here; Cloudflare shows the secret only once.":
        "اضغطوا Create وانسخوا ⁦Access Key ID⁩ و⁦Secret Access Key⁩ إلى هنا. يعرض Cloudflare المفتاح السري مرة واحدة فقط.",
    "Copy the account ID from the R2 overview page (or from the endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com).":
        "انسخوا رقم الحساب (⁦Account ID⁩) من صفحة R2 الرئيسية، أو من العنوان https://ACCOUNT_ID.r2.cloudflarestorage.com.",
    "Choose a passphrase, save it in a password manager, then press Test and save, and turn on Technting Backup in Plugins.":
        "اختاروا عبارة مرور واحفظوها في برنامج لحفظ كلمات المرور، ثم اضغطوا «تجربة وحفظ» وفعّلوا ⁦Technting Backup⁩ من «الإضافات».",
    "Backblaze B2: create a private bucket, set its lifecycle to “Keep only the last version”, and create an application key for that bucket only (Read and Write). The keyID is the access key ID.":
        "⁦Backblaze B2⁩: أنشئوا حاوية خاصة (Private)، واجعلوا إعداد Lifecycle «⁦Keep only the last version⁩»، وأنشئوا ⁦Application Key⁩ لهذه الحاوية فقط بصلاحية القراءة والكتابة. قيمة keyID هي معرّف مفتاح الوصول.",
    # messages
    "Offsite settings removed. Copies already in the bucket were not deleted.": "حُذفت إعدادات النسخ خارج الخادم. لم تُحذف النسخ الموجودة في الحاوية.",
    "Enter the secret access key.": "أدخلوا المفتاح السري.", "The passphrase must be at least 12 characters.": "يجب أن تكون عبارة المرور 12 حرفاً على الأقل.",
    "The two passphrases are not the same.": "عبارتا المرور غير متطابقتين.",
    "Confirm that you saved the passphrase somewhere safe.": "أكّدوا أنكم حفظتم عبارة المرور في مكان آمن.",
    "The storage refused the test:": "رفض التخزين التجربة:", "Could not reach the storage:": "تعذّر الوصول إلى التخزين:",
    "Connection works. Offsite settings saved. The newest backup is copied within 5 minutes.":
        "الاتصال يعمل وحُفظت الإعدادات. ستُنسخ أحدث نسخة احتياطية خلال 5 دقائق.",
    "Copies made before today need the old passphrase. Keep it until they are removed by the retention policy.":
        "النسخ التي صُنعت قبل اليوم تحتاج إلى عبارة المرور القديمة. احتفظوا بها حتى تُحذف تلك النسخ تلقائياً.",
    "Add your email address in My account to receive alerts.": "أضيفوا بريدكم الإلكتروني في «حسابي» لتصلكم التنبيهات.",
    "Started. Reload this page in a minute to see the result.": "بدأت العملية. حدّثوا الصفحة بعد دقيقة لرؤية النتيجة.",
    "Another offsite job is running. Try again in a few minutes.": "توجد عملية أخرى قيد التشغيل. حاولوا بعد بضع دقائق.",
    "Choose a storage provider.": "اختاروا مزوّد التخزين.",
    "The Cloudflare account ID is 32 letters and numbers (R2 → Overview).": "رقم حساب Cloudflare مكوّن من 32 حرفاً ورقماً (تجدونه في R2 ثم Overview).",
    "Enter the Backblaze region, for example us-west-004.": "أدخلوا منطقة Backblaze، مثل ⁦us-west-004⁩.",
    "Enter the storage address, starting with https://": "أدخلوا عنوان التخزين، ويبدأ بـ https://",
    "Enter the bucket name (small letters, numbers and dashes).": "أدخلوا اسم الحاوية (حروف إنجليزية صغيرة وأرقام وشرطات).",
    "The folder name may use letters, numbers, dots, dashes and /.": "اسم المجلد يقبل الحروف والأرقام والنقاط والشرطات و/.",
    "Enter the access key ID.": "أدخلوا معرّف مفتاح الوصول.", "Keep between 0 and 400 copies.": "يجب أن يكون عدد النسخ بين 0 و400.",
    "Keep at least one daily copy.": "احتفظوا بنسخة يومية واحدة على الأقل.",
    # problems (Backups page, security page, alert emails, weekly summary)
    "The last backup is more than 36 hours old": "مرّ على آخر نسخة احتياطية أكثر من 36 ساعة",
    "The last backup failed": "فشلت آخر عملية نسخ احتياطي", "Offsite backups are not set up": "النسخ خارج الخادم غير مُعدّة",
    "Copying the backup offsite failed": "فشل نسخ النسخة الاحتياطية إلى خارج الخادم",
    "The newest offsite copy is more than 36 hours old": "مرّ على أحدث نسخة خارج الخادم أكثر من 36 ساعة",
    "The offsite copies failed the integrity check": "فشلت النسخ الخارجية في فحص السلامة",
    "The monthly restore test failed": "فشلت تجربة الاسترجاع الشهرية", "No restore test in the last 40 days": "لم تُجرَّب استعادة أي نسخة منذ 40 يوماً",
    "Backups are kept only on the server (turn on Technting Backup)": "النسخ الاحتياطية محفوظة على الخادم فقط (فعّلوا ⁦Technting Backup⁩)",
    # copies list, storage limit, retention (round 2)
    "Kept as": "سبب الاحتفاظ", "newest": "الأحدث",
    "Download from the storage and decrypt": "تنزيل من التخزين وفك التشفير", "Download failed:": "فشل التنزيل:",
    "Download gets the copy from the storage and decrypts it on the server; it may take a minute. Copies outside the plan are removed once a day.":
        "التنزيل يجلب النسخة من التخزين ويفك تشفيرها على الخادم، وقد يستغرق دقيقة. النسخ الزائدة عن الخطة تُحذف مرة في اليوم.",
    "Storage limit (GB)": "حد التخزين (GB)",
    "R2 and B2 are free up to 10 GB. You get a warning at 80%. Use 0 for no limit.":
        "R2 وB2 مجانيان حتى 10 GB. يصلكم تنبيه عند 80%. اكتبوا 0 إذا لم يكن هناك حد.",
    "Enter the storage limit in GB (0 for no limit).": "أدخلوا حد التخزين بالـ GB (أو 0 بلا حد).",
    "Old offsite copies could not be removed": "تعذّر حذف النسخ الخارجية القديمة",
    "Some old offsite copies cannot be deleted (check the bucket lock)": "بعض النسخ الخارجية القديمة لا يمكن حذفها (راجعوا قفل الحاوية)",
    "Offsite storage is almost full": "مساحة التخزين الخارجي قاربت على الامتلاء",
    "copies": "نسخ",
}.items():
    AR.setdefault(_k, _v)
COUNT_AR.setdefault("copies", ("نسخة", "نسختان", "نسخ", "نسخة", "نسخة", "لا توجد نسخ"))

# Technting Backup: Google Drive as offsite storage
for _k, _v in {
    "Google client ID":
        "معرّف عميل Google (⁦Client ID⁩)",
    "Google client secret":
        "كلمة سر عميل Google (⁦Client secret⁩)",
    "Leave empty to keep the saved secret.":
        "اتركوه فارغاً للإبقاء على كلمة السر المحفوظة.",
    "Folder in Google Drive":
        "المجلد في ⁦Google Drive⁩",
    "Technting CMS creates this folder and can see only the files it puts there, nothing else in the Drive.":
        "ينشئ ⁦Technting CMS⁩ هذا المجلد، ولا يرى إلا الملفات التي يضعها فيه، ولا يرى أي شيء آخر في ⁦Drive⁩.",
    "Open this address on any phone or computer, enter the code, choose the Google account for the backups and press Allow:":
        "افتحوا هذا العنوان على أي هاتف أو حاسوب، واكتبوا الرمز، واختاروا حساب Google الذي ستُحفظ فيه النسخ، ثم اضغطوا Allow:",
    "I allowed access, finish connecting":
        "سمحتُ بالوصول، أكمِلوا الربط",
    "New code":
        "رمز جديد",
    "Google Drive is connected.":
        "تم ربط ⁦Google Drive⁩.",
    "Connect again":
        "الربط من جديد",
    "Connect Google Drive":
        "ربط ⁦Google Drive⁩",
    "Google shows a short code. You enter it at google.com/device to allow access.":
        "سيعرض Google رمزاً قصيراً، تكتبونه في ⁦google.com/device⁩ للسماح بالوصول.",
    "Set up Google Drive":
        "إعداد ⁦Google Drive⁩",
    "Open console.cloud.google.com with the Google account that will keep the backups. Create a project, for example “Technting CMS backups”.":
        "افتحوا ⁦console.cloud.google.com⁩ بحساب Google الذي ستُحفظ فيه النسخ، وأنشئوا مشروعاً (Project) باسم مثل «⁦Technting CMS backups⁩».",
    "APIs & Services → Library: search for Google Drive API and press Enable.":
        "من ⁦APIs & Services⁩ افتحوا Library، وابحثوا عن ⁦Google Drive API⁩ واضغطوا Enable.",
    "Google Auth Platform → Branding: enter an app name (Technting CMS backups) and your email, then save.":
        "من ⁦Google Auth Platform⁩ افتحوا Branding، واكتبوا اسماً للتطبيق (⁦Technting CMS backups⁩) وبريدكم، ثم احفظوا.",
    "Audience: choose Internal if you use Google Workspace. Otherwise choose External and press Publish app. Do not leave it in Testing: Google stops the access after 7 days. This app only asks for its own files (drive.file), so Google does not need to review it.":
        "في Audience اختاروا Internal إذا كنتم تستخدمون ⁦Google Workspace⁩، وإلا فاختاروا External ثم اضغطوا ⁦Publish app⁩. لا تتركوه على Testing، لأن Google يوقف الوصول بعد 7 أيام. التطبيق لا يطلب إلا ملفاته (⁦drive.file⁩)، لذلك لا يحتاج إلى مراجعة من Google.",
    "Clients → Create client. Application type: TVs and Limited Input devices. Copy the Client ID and the Client secret here.":
        "من Clients اضغطوا ⁦Create client⁩، واختاروا نوع التطبيق ⁦TVs and Limited Input devices⁩. انسخوا ⁦Client ID⁩ و⁦Client secret⁩ إلى هنا.",
    "Press Connect Google Drive. Open google.com/device on your phone or computer, enter the code, choose the same account and press Allow. Then press “I allowed access”.":
        "اضغطوا «ربط ⁦Google Drive⁩». افتحوا ⁦google.com/device⁩ على هاتفكم أو حاسوبكم، واكتبوا الرمز، واختاروا الحساب نفسه، ثم اضغطوا Allow. بعدها اضغطوا «سمحتُ بالوصول».",
    "Free Google accounts have 15 GB shared with Gmail. Cloudflare R2 stays the better choice for large sites.":
        "في حساب Google المجاني مساحة 15 GB مشتركة مع Gmail. يبقى ⁦Cloudflare R2⁩ الخيار الأفضل للمواقع الكبيرة.",
    # messages
    "The Google client ID ends with .apps.googleusercontent.com":
        "معرّف عميل Google ينتهي بـ ⁦.apps.googleusercontent.com⁩",
    "The Google Drive folder name may use letters, numbers, spaces, dots and dashes.":
        "اسم المجلد في ⁦Google Drive⁩ يقبل الحروف الإنجليزية والأرقام والمسافات والنقاط والشرطات.",
    "Enter the Google client secret.":
        "أدخلوا كلمة سر عميل Google (⁦Client secret⁩).",
    "Google refused:":
        "رفض Google الطلب:",
    "Could not reach Google:":
        "تعذّر الوصول إلى Google:",
    "Press Connect Google Drive first.":
        "اضغطوا «ربط ⁦Google Drive⁩» أولاً.",
    "The code expired. Press Connect Google Drive again.":
        "انتهت مدة الرمز. اضغطوا «ربط ⁦Google Drive⁩» مرة أخرى.",
    "Google is still waiting. Wait a few seconds and press the button again.":
        "ما زال Google ينتظر. انتظروا بضع ثوانٍ ثم اضغطوا الزر مرة أخرى.",
    "Access was refused in Google. Press Connect Google Drive to try again.":
        "لم يُسمح بالوصول في Google. اضغطوا «ربط ⁦Google Drive⁩» للمحاولة مرة أخرى.",
    "Google is still waiting. Enter the code at the address shown, allow access, then press the button again.":
        "ما زال Google ينتظر. اكتبوا الرمز في العنوان الظاهر واسمحوا بالوصول، ثم اضغطوا الزر مرة أخرى.",
    "Google Drive is connected. Now set the passphrase and press Test and save.":
        "تم ربط ⁦Google Drive⁩. الآن ضعوا عبارة المرور واضغطوا «تجربة وحفظ».",
    "Connect Google Drive first: press Connect Google Drive and allow access.":
        "اربطوا ⁦Google Drive⁩ أولاً: اضغطوا «ربط ⁦Google Drive⁩» واسمحوا بالوصول.",
}.items():
    AR.setdefault(_k, _v)

# Lead forms on service pages and articles; setdefault keeps any wording already chosen for the same English text
for _k, _v in {
    "Came from": "مصدر الاستفسار", "Service": "الخدمة", "Email copy": "نسخة البريد", "Sent": "أُرسلت",
    "Not chosen": "لم تُحدَّد", "Any website form": "كل نماذج الموقع", "Service pages": "صفحات الخدمات",
    "Use case pages": "صفحات حالات الاستخدام", "Articles": "المقالات", "Other pages": "صفحات أخرى",
    "Header form": "نموذج أعلى الموقع", "email not sent": "لم يُرسل البريد",
    "Enquiries whose email was not sent": "استفسارات لم يُرسل بريدها",
    "They are saved here; open one to send the email again.": "هي محفوظة هنا، افتحوا أياً منها لإرسال البريد مرة أخرى.",
    "Show them": "اعرضوها", "Leads email": "بريد العملاء المحتملين",
    "Every enquiry from the website forms is emailed here, and also saved in the Inbox and the CRM.":
        "يُرسل كل استفسار من نماذج الموقع إلى هذا البريد، ويُحفظ أيضاً في صندوق الوارد ونظام إدارة العملاء.",
    "The leads email address is not valid. It was not changed.": "بريد العملاء المحتملين غير صحيح، ولم يتم تغييره.",
    "Email sent to": "أُرسل البريد إلى",
    "The email could not be sent. The enquiry is still saved here.": "تعذّر إرسال البريد، والاستفسار ما زال محفوظاً هنا.",
    "This enquiry was saved, but the email to the team was not sent.": "حُفظ هذا الاستفسار، لكن لم يُرسل البريد إلى الفريق.",
    "Send the email again": "إرسال البريد مرة أخرى", "Enquiries by page": "الاستفسارات حسب الصفحة",
    "Enquiries from website forms": "استفسارات من نماذج الموقع",
}.items():
    AR.setdefault(_k, _v)


def count(n, key, lang):
    """'78 pages checked' / 'صفحتان مفحوصتان' / '44 رابطاً'."""
    forms = COUNT_AR.get(key) if lang == "ar" else None
    if not forms:
        return f"{n} {tr(key, lang)}"
    try:
        k = int(n)
    except (TypeError, ValueError):
        return f"{n} {forms[2]}"
    one, two, few, many, many_acc, zero = forms
    if k == 0:
        return zero or f"0 {many}"
    if k == 2:
        return two
    if 3 <= k <= 10:
        return f"{k} {few}"
    return f"{k} {many_acc if 11 <= k % 100 <= 99 else many}"


def publish_summary(message, lang):
    """The publish log line ("78 pages, 3 files updated, 0 removed in 1.3s") in the editor's language."""
    import re
    m = re.fullmatch(r"(\d+) pages, (\d+) files updated, (\d+) removed in ([\d.]+)s", message or "")
    if lang != "ar" or not m:
        return message
    pages, changed, removed, secs = m.groups()
    return f"{count(pages, 'pages', lang)} · الملفات المحدّثة: {changed} · المحذوفة: {removed} · المدة: {secs} ث"

AR.update({
    "English": "الإنجليزية", "Arabic": "العربية", "home": "الرئيسية", "default": "افتراضي", "record": "سجل",
    "Websites": "المواقع", "Marketing": "التسويق", "Support": "الدعم",
    "Not sure yet": "غير متأكد بعد",
    "saved and published.": "حُفظ ونُشر.", "Saved, but publishing failed:": "حُفظ، لكن النشر فشل:", "Draft saved.": "حُفظت المسودة.",
    "Saved.": "تم الحفظ.", "Site published.": "نُشر الموقع.", "Publishing failed:": "فشل النشر:", "Enquiry deleted permanently.": "حُذف الاستفسار نهائياً.",
    "Page": "الصفحة", "Site": "الموقع", "Menus": "القوائم", "Settings": "الإعدادات", "Redirect": "التحويل",
})

# Technting SEO (SEO page, plugin secrets, article SEO check, site health); setdefault keeps any wording already chosen
for _k, _v in {
    "This is not a valid JSON file, so it was not saved:": "هذا ليس ملف JSON صالحاً، لذلك لم يُحفظ:",
    "Google service account key (JSON file)": "مفتاح حساب الخدمة من Google (ملف JSON)",
    "Searches that show this page on Google (28 days)": "عبارات البحث التي تُظهر هذه الصفحة في Google (آخر 28 يوماً)",
    "Search term": "عبارة البحث", "Clicks": "النقرات", "Shown": "مرات الظهور", "Position": "الترتيب", "page 2": "الصفحة الثانية",
    "Searches on page 2 (positions 11 to 20) are the quickest wins: use their words in a subheading and in the first paragraph.":
        "عبارات البحث في الصفحة الثانية (الترتيب من 11 إلى 20) أسرع ما يمكن تحسينه: استخدموا كلماتها في عنوان فرعي وفي الفقرة الأولى.",
    "People search Google for these words and find that page": "يبحث الناس في Google بهذه الكلمات فيجدون تلك الصفحة",
    "Keyword in a subheading (H2)": "الكلمة المفتاحية في عنوان فرعي (H2)",
    "Keyword used naturally (0.5 to 2.5% of the words)": "الكلمة المفتاحية مستخدمة باعتدال (من 0.5 إلى 2.5% من الكلمات)",
    "Short sentences (under 20 words on average)": "جمل قصيرة (أقل من 20 كلمة في المتوسط)",
    "Short sentences (under 25 words on average)": "جمل قصيرة (أقل من 25 كلمة في المتوسط)",
    "Short paragraphs (under 150 words)": "فقرات قصيرة (أقل من 150 كلمة)",
    "A subheading at least every 350 words": "عنوان فرعي كل 350 كلمة على الأكثر",
    "Structured data and sharing image are checked after publishing": "تُفحص البيانات المنظّمة وصورة المشاركة بعد النشر",
    "Structured data (JSON-LD) is valid": "البيانات المنظّمة (JSON-LD) سليمة",
    "Sharing image at least 1200×630": "صورة المشاركة بحجم 1200×630 على الأقل",
    "Search: structured data (JSON-LD) with errors": "البحث: أخطاء في البيانات المنظّمة (JSON-LD)",
    "Sharing image missing or smaller than 1200×630": "صورة المشاركة غير موجودة أو أصغر من 1200×630",
    "Google search": "البحث في Google", "Index status (Google)": "حالة الصفحات في Google",
    "Connected": "متصل", "Problem": "مشكلة", "Waiting for the first check": "بانتظار أول فحص",
    "Refreshing…": "جارٍ التحديث…", "Refresh now": "تحديث الآن", "Check speed again": "إعادة فحص السرعة",
    "Starts a new PageSpeed round; two pages are checked now, the rest every few minutes.":
        "يبدأ جولة PageSpeed جديدة: تُفحص صفحتان الآن والباقي كل بضع دقائق.",
    "Technting SEO is off. Follow the setup steps below, then turn it on in Plugins.":
        "إضافة Technting SEO متوقفة. اتبعوا خطوات الإعداد أدناه، ثم فعّلوها من «الإضافات».",
    "No service account key uploaded.": "لم يُرفع مفتاح حساب الخدمة بعد.",
    "This file is not a service account key. Download a JSON key from the service account's Keys tab.":
        "هذا الملف ليس مفتاح حساب خدمة. نزّلوا مفتاح JSON من تبويب Keys في حساب الخدمة.",
    "Google refused access. Add the service account email as a user in Search Console and check the property address.":
        "رفض Google الوصول. أضيفوا بريد حساب الخدمة كمستخدم في Search Console، وتأكدوا من عنوان الموقع.",
    "Search Console has no property with this address. Check the property address in the plugin settings.":
        "لا يوجد موقع بهذا العنوان في Search Console. راجعوا العنوان في إعدادات الإضافة.",
    "Google did not accept the key file. Upload a new JSON key.": "لم يقبل Google ملف المفتاح. ارفعوا مفتاح JSON جديداً.",
    "The free daily limit is used up. It tries again later by itself.": "انتهى الحد المجاني لهذا اليوم، وستُعاد المحاولة لاحقاً تلقائياً.",
    "The PageSpeed key was not accepted. Check the key and that PageSpeed Insights API is turned on in Google Cloud.":
        "لم يُقبل مفتاح PageSpeed. تأكدوا من المفتاح ومن تفعيل PageSpeed Insights API في Google Cloud.",
    "Bing did not accept the key, or the site is not in Bing Webmaster Tools yet.":
        "لم يقبل Bing المفتاح، أو أن الموقع غير مضاف إلى Bing Webmaster Tools بعد.",
    "The service did not answer as expected. It tries again later.": "لم تُجب الخدمة كما يجب، وستُعاد المحاولة لاحقاً.",
    "compared with the 28 days before": "مقارنة بالأيام الـ28 التي قبلها", "updated": "آخر تحديث",
    "Times shown in Google": "مرات الظهور في Google", "Click rate (CTR)": "نسبة النقر (CTR)", "Average position": "متوسط الترتيب",
    "Clicks and times shown per day": "النقرات ومرات الظهور يومياً",
    "Faded bars are the 28 days before, for comparison.": "الأعمدة الباهتة هي الأيام الـ28 التي قبلها، للمقارنة.",
    "English and Arabic pages": "الصفحات الإنجليزية والعربية", "No data yet.": "لا توجد بيانات بعد.",
    "Pages losing clicks": "صفحات تخسر نقرات", "Before": "قبل", "Now": "الآن", "No page lost clicks. Good.": "لم تخسر أي صفحة نقرات. ممتاز.",
    "Check that the page is still up to date, still answers the search, and still has links from newer articles.":
        "تأكدوا أن الصفحة ما زالت محدّثة، وأنها تجيب عمّا يبحث عنه الناس، وأن المقالات الأحدث تضع روابط إليها.",
    "Searches on page 2 worth improving": "عبارات بحث في الصفحة الثانية تستحق التحسين",
    "Positions 11 to 20: a small push brings them to page 1.": "الترتيب من 11 إلى 20: تحسين بسيط ينقلها إلى الصفحة الأولى.",
    "None right now.": "لا يوجد حالياً.",
    "Use the search words in a subheading and the first paragraph, answer the question more fully, and link to the page from related articles.":
        "استخدموا كلمات البحث في عنوان فرعي وفي الفقرة الأولى، وأجيبوا عن السؤال بتفصيل أكثر، وضعوا روابط إلى الصفحة من مقالات قريبة من موضوعها.",
    "Shown often but rarely clicked": "تظهر كثيراً لكن قلّما يُنقر عليها",
    "Rewrite the SEO title and description to match what people search for.": "أعيدوا كتابة عنوان SEO ووصفه ليطابقا ما يبحث عنه الناس.",
    "Top searches": "أكثر عبارات البحث", "Pages with the most clicks": "الصفحات الأكثر نقراً",
    "Is Google showing our key pages?": "هل تظهر صفحاتنا المهمة في Google؟", "in Google": "في Google",
    "Last visit by Google": "آخر زيارة من Google", "Could not check": "تعذّر الفحص", "In Google": "في Google",
    "Not in Google yet": "ليست في Google بعد", "Google picked a different main address:": "اختار Google رابطاً رئيسياً مختلفاً:",
    "Checked once a week: the home and blog pages and the newest articles in both languages. To ask Google to visit a page sooner, use URL inspection in Search Console.":
        "يُفحص مرة كل أسبوع: الصفحة الرئيسية وصفحة المقالات وأحدث المقالات باللغتين. لتطلبوا من Google زيارة صفحة بسرعة، استخدموا URL inspection في Search Console.",
    "Submitted and indexed": "موجودة في Google ومرسلة في خريطة الموقع",
    "Indexed, not submitted in sitemap": "موجودة في Google لكنها ليست في خريطة الموقع",
    "Crawled - currently not indexed": "زارها Google لكنه لم يضفها بعد",
    "Discovered - currently not indexed": "يعرفها Google لكنه لم يزرها بعد",
    "URL is unknown to Google": "لا يعرف Google هذا الرابط بعد", "Page with redirect": "صفحة تُحوِّل إلى صفحة أخرى",
    "Duplicate without user-selected canonical": "مكررة دون تحديد الرابط الرئيسي",
    "Alternate page with proper canonical tag": "نسخة بديلة لها رابط رئيسي صحيح",
    "Excluded by ‘noindex’ tag": "مستبعدة بوسم noindex", "Not found (404)": "غير موجودة (404)",
    "Speed on mobile (PageSpeed Insights)": "السرعة على الجوال (PageSpeed Insights)", "pages still waiting:": "صفحات بانتظار الفحص:",
    "Speed": "السرعة", "Accessibility": "سهولة الوصول", "Best practices": "أفضل الممارسات",
    "Not enough real visits yet (lab test only)": "لا توجد زيارات حقيقية كافية بعد (فحص تجريبي فقط)",
    "Scores are out of 100 (90+ is good). LCP, INP and CLS come from real Chrome visitors over 28 days: green is good, amber needs work, red is poor. * means the whole site's figures, because the page has too few visits of its own. Checked once a month.":
        "النتائج من 100 (من 90 فأعلى جيدة). أرقام LCP وINP وCLS من زوار حقيقيين يستخدمون Chrome خلال 28 يوماً: الأخضر جيد، والبرتقالي يحتاج إلى تحسين، والأحمر ضعيف. علامة * تعني أرقام الموقع كله، لأن زيارات الصفحة وحدها قليلة. يُفحص مرة كل شهر.",
    "since": "منذ", "optional": "اختياري",
    "How to connect Google, PageSpeed and Bing (free)": "طريقة ربط Google وPageSpeed وBing (مجاناً)",
    "Open console.cloud.google.com with the Google account that owns Search Console, and create a project (for example technting-cms-seo).":
        "افتحوا console.cloud.google.com بحساب Google الذي يملك Search Console، وأنشئوا مشروعاً جديداً (مثلاً technting-cms-seo).",
    "Go to APIs & Services → Library, search for “Google Search Console API” and press Enable. Do the same for “PageSpeed Insights API”.":
        "اذهبوا إلى APIs & Services ← Library، وابحثوا عن «Google Search Console API» واضغطوا Enable. كرّروا الخطوة نفسها مع «PageSpeed Insights API».",
    "Go to APIs & Services → Credentials → Create credentials → Service account. Give it a name (for example technting-cms-seo) and press Done. It needs no roles.":
        "اذهبوا إلى APIs & Services ← Credentials ← Create credentials ← Service account. اكتبوا اسماً (مثلاً technting-cms-seo) ثم اضغطوا Done. لا يحتاج إلى أي صلاحيات (roles).",
    "Open the new service account → Keys → Add key → Create new key → JSON. A .json file downloads. Keep it private.":
        "افتحوا حساب الخدمة الجديد ← Keys ← Add key ← Create new key ← JSON. سيُنزَّل ملف ‎.json‎، احتفظوا به ولا تشاركوه مع أحد.",
    "Copy the service account's email (it ends with iam.gserviceaccount.com).": "انسخوا بريد حساب الخدمة (ينتهي بـ iam.gserviceaccount.com).",
    "Open search.google.com/search-console → Settings → Users and permissions → Add user. Paste the email and choose Full permission.":
        "افتحوا search.google.com/search-console ← Settings ← Users and permissions ← Add user. الصقوا البريد واختاروا صلاحية Full.",
    "Here in the dashboard: Plugins → Technting SEO → choose the .json file under “Google service account key”, turn the plugin on and save.":
        "هنا في لوحة التحكم: الإضافات ← Technting SEO ← اختاروا ملف ‎.json‎ في خانة «مفتاح حساب الخدمة من Google»، ثم فعّلوا الإضافة واحفظوا.",
    "Come back to this page and press Refresh now. Search data appears within a minute; Google's figures run about 3 days behind.":
        "ارجعوا إلى هذه الصفحة واضغطوا «تحديث الآن». تظهر بيانات البحث خلال دقيقة، وأرقام Google تتأخر عادةً نحو 3 أيام.",
    "In the same Google Cloud project: APIs & Services → Credentials → Create credentials → API key.":
        "في مشروع Google Cloud نفسه: APIs & Services ← Credentials ← Create credentials ← API key.",
    "Press Edit API key → API restrictions → Restrict key, choose PageSpeed Insights API and press Save.":
        "اضغطوا Edit API key ← API restrictions ← Restrict key، واختاروا PageSpeed Insights API ثم اضغطوا Save.",
    "Copy the key and paste it in Plugins → Technting SEO → PageSpeed Insights API key. Pages are checked once a month, two at a time.":
        "انسخوا المفتاح والصقوه في الإضافات ← Technting SEO ← مفتاح PageSpeed Insights. تُفحص الصفحات مرة كل شهر، صفحتين في كل مرة.",
    "Open bing.com/webmasters and sign in. Choose Import from Google Search Console to add the site in one step.":
        "افتحوا bing.com/webmasters وسجّلوا الدخول. اختاروا Import from Google Search Console لإضافة الموقع بخطوة واحدة.",
    "Open Settings (the gear) → API access → API Key → Generate, and copy the key.":
        "افتحوا Settings (رمز الترس) ← API access ← API Key ← Generate، وانسخوا المفتاح.",
    "Paste it in Plugins → Technting SEO → Bing Webmaster Tools API key and save.":
        "الصقوه في الإضافات ← Technting SEO ← مفتاح Bing Webmaster Tools، ثم احفظوا.",
    "The key file and the keys are stored encrypted and are never shown again. To stop access at any time, delete the key in Google Cloud or remove the user in Search Console.":
        "يُحفظ ملف المفتاح والمفاتيح مشفّرة ولا تظهر مرة أخرى. لإيقاف الوصول في أي وقت احذفوا المفتاح من Google Cloud أو احذفوا المستخدم من Search Console.",
    "Turn on Technting SEO in Plugins first.": "فعّلوا Technting SEO من «الإضافات» أولاً.",
    "Refreshing in the background. Reload this page in a minute or two.": "يجري التحديث في الخلفية. أعيدوا تحميل الصفحة بعد دقيقة أو دقيقتين.",
    "A refresh is already running.": "يوجد تحديث يعمل الآن.",
    "Last 28 days": "آخر 28 يوماً", "Searches on page 2": "عبارات في الصفحة الثانية",
    "Articles and their focus keywords": "المقالات وكلماتها المفتاحية", "Google position on": "الترتيب في Google بتاريخ",
    "without a focus keyword:": "بلا كلمة مفتاحية:", "Article": "المقال", "Focus keyword": "الكلمة المفتاحية",
    "7 days": "7 أيام", "28 days": "28 يوماً", "SEO score": "نتيجة SEO", "Not set": "غير محددة",
    "Google shows another page:": "يُظهر Google صفحة أخرى:", "Not in the first results yet": "ليست في النتائج الأولى بعد",
    "Position is Google's average over 28 days; +3 means three places higher (better). Positions are kept every day, so the changes fill in over the first weeks.":
        "الترتيب هو متوسط Google خلال 28 يوماً، و+3 تعني تقدّم ثلاثة مراكز (أفضل). يُحفظ الترتيب كل يوم، لذلك تكتمل أرقام التغيّر خلال الأسابيع الأولى.",
    "Sitemap in Search Console": "خريطة الموقع في Search Console", "Not sent yet": "لم تُرسل بعد",
    "Send the sitemap in Search Console → Sitemaps:": "أرسلوا خريطة الموقع من Search Console ← Sitemaps:",
    "Sitemap": "خريطة الموقع", "Last read by Google": "آخر قراءة من Google", "Addresses": "الروابط", "Errors": "الأخطاء",
    "Warnings": "التحذيرات", "waiting": "قيد الانتظار",
}.items():
    AR.setdefault(_k, _v)

# public demo mode (cms/demo.py)
for _k, _v in {
    "Public demo": "نسخة تجريبية عامة",
    "This is a public demo. Everything resets every 2 hours. Do not enter real personal data.":
        "هذه نسخة تجريبية مفتوحة للجميع، ويُعاد ضبط كل شيء كل ساعتين. لا تكتبوا فيها أي بيانات شخصية حقيقية.",
    "The username or password is not correct.": "اسم المستخدم أو كلمة المرور غير صحيحة.",
    "This is turned off in the public demo, so the demo stays safe for everyone.":
        "هذه الميزة متوقفة في النسخة التجريبية العامة، حفاظاً على سلامة العرض للجميع.",
    "Demo sign-in": "بيانات الدخول التجريبية",
    "Files with this extension cannot be uploaded.": "لا يمكن رفع ملفات بهذا الامتداد.",
    "In the public demo, only JPEG, PNG, WebP, GIF and PDF files up to 5 MB can be uploaded.":
        "في النسخة التجريبية العامة لا يمكن رفع إلا ملفات JPEG وPNG وWebP وGIF وPDF، بحجم لا يزيد على 5 ميغابايت.",
    "The file extension does not match its content.": "امتداد الملف لا يطابق محتواه.",
    "PDF files with scripts or attachments cannot be uploaded in the public demo.":
        "لا يمكن رفع ملفات PDF تحتوي على نصوص برمجية أو مرفقات في النسخة التجريبية العامة.",
    "The demo media library is full. Delete some files first.": "مكتبة الوسائط في النسخة التجريبية ممتلئة. احذفوا بعض الملفات أولاً.",
    "Custom HTML blocks are turned off in the public demo. Remove the block and save again. Nothing was saved.":
        "أقسام HTML المخصصة متوقفة في النسخة التجريبية العامة. احذفوا القسم ثم احفظوا مرة أخرى، فلم يُحفظ أي شيء.",
    "In the public demo, the replacement text cannot contain < or >.":
        "في النسخة التجريبية العامة لا يمكن أن يحتوي نص الاستبدال على الرمزين < و>.",
}.items():
    AR.setdefault(_k, _v)
