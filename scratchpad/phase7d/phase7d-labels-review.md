# Phase 7D Stage 2.2 — пакет для reviewer verification

Официальный sample: 103 строки (100 random + 3 amendment), byte sha256 `873ee2a19e7dedbc322357f8ff4108690b4e3f6a25889571e13c5f7191bfdeb8`.
Analyst (агент) разметил все 103 строки по разрешённым источникам (факты строки, snapshot taxonomy, derivation doc v2; без веб-поиска).

**Analyst distribution:** correct=103, incorrect=0, identity_problem=0, taxonomy_gap=0, unverifiable=0.

Единогласная разметка analyst — НЕ основание для автоматического принятия: по D-2 reviewer
обязан независимо проверить (а) все monitoring-строки, (б) все не-correct (нет таких),
(в) ≥20 случайных analyst-correct. Reviewer может изменить decision, изменить rationale
или оставить analyst rationale без изменений. Для изменения решения ответьте в формате:
`id=<product_id> decision=<enum> rationale=<текст>`; для правки только текста: `id=<product_id> rationale=<текст>`.

## A. Monitoring-строки (обязательная проверка) — 13

- **422** [MON: tt-bp-vozdukhoduvki-akkum] [AMENDMENT] | Воздуходувка аккум DENZEL RB180-36, Li-ion 36В 4Ач, 180км/ч 820м3/ч 2 аккум 18В 4Ач | art=59610 | sg=Аккумуляторный инструмент
  → slug `bp-vozdukhoduvki` (Воздуходувки) | refs `tt-bp-vozdukhoduvki-akkum`
  → analyst: **correct** — Аккумуляторная воздуходувка — slug «Воздуходувки»; тип не зависит от источника питания (review правила 8). MONITORING.
- **1857** [MON: tt-yashchiki-sumki-benzopila] | Сумка для бензопилы тем.сер+оранж | art=OZONE R-7125 | sg=Бензоинструмент и расходники для них
  → slug `yashchiki-sumki` (Ящики, сумки, органайзеры) | refs `tt-yashchiki-sumki-benzopila`
  → analyst: **correct** — Сумка для бензопилы — slug «Ящики, сумки, органайзеры». MONITORING (правило 20).
- **1858** [MON: tt-yashchiki-sumki-benzopila] | Сумка для бензопилы темно-синий | art=OZONE R-5112 | sg=Бензоинструмент и расходники для них
  → slug `yashchiki-sumki` (Ящики, сумки, органайзеры) | refs `tt-yashchiki-sumki-benzopila`
  → analyst: **correct** — Сумка для бензопилы — slug «Ящики, сумки, органайзеры». MONITORING (правило 20).
- **10807** [MON: tt-izm-kolesa-dorozhnoe] | Колесо дорожное BOSCH GWM 32, 10000м, 0.5 мм/м, Диаметр колеса 31.9 см, Вес 2 кг | art=0601074000 | sg=Измерительный инструмент
  → slug `izm-kolesa` (Измерительные колёса (курвиметры)) | refs `tt-izm-kolesa-dorozhnoe`
  → analyst: **correct** — Дорожное измерительное колесо BOSCH — slug «Измерительные колёса (курвиметры)». MONITORING (правило 17).
- **29557** [MON: tt-siz-izveshchateli-gromkogovoritel] [AMENDMENT] | Громкоговоритель HS-10-A (INTER-M) рупорный 10Вт | art=216632 | sg=Пожарка
  → slug `siz-izveshchateli` (Извещатели и оповещатели) | refs `tt-siz-izveshchateli-gromkogovoritel`
  → analyst: **correct** — Рупорный громкоговоритель 10Вт (sg=Пожарка) — slug «Извещатели и оповещатели»: оповещатель по значению slug; MONITORING (правило 26), прецедентов наполнения slug нет — обязательная проверка reviewer.
- **29733** [MON: tt-siz-pozh-inventar-polotno] [AMENDMENT] | Полотно противопожарное ПП-1000 (1,5*2,0) (до 1000 | art=ОГН-ПП1000 | sg=Пожарка
  → slug `siz-pozh-inventar` (Пожарный инвентарь) | refs `tt-siz-pozh-inventar-polotno`
  → analyst: **correct** — Противопожарное полотно ПП-1000 — slug «Пожарный инвентарь». MONITORING (правило 22).
- **31973** [MON: tt-obor-mebel-verstak] | Верстак Bosch PTA 1000 для PCM7; высота 700-1150мм | art=BSH-0603B05100 | sg=Слесарно-столярный инструмент
  → slug `obor-mebel` (Верстаки и мебель мастерской) | refs `tt-obor-mebel-verstak`
  → analyst: **correct** — Верстак Bosch PTA 1000 — slug «Верстаки и мебель мастерской». MONITORING (правило 13).
- **31974** [MON: tt-obor-mebel-verstak] | Верстак Bosch PTA 2400 для PCM8S; высота 800мм, дл | art=BSH-0603B05000 | sg=Слесарно-столярный инструмент
  → slug `obor-mebel` (Верстаки и мебель мастерской) | refs `tt-obor-mebel-verstak`
  → analyst: **correct** — Верстак Bosch PTA 2400 — slug «Верстаки и мебель мастерской». MONITORING (правило 13).
- **36301** [MON: tt-siz-ochki-shitok] | Маска щиток защитный лицевой ЕВРО закрытый НБТ-2 | art=РСВ-64445 | sg=Средства индивидуальной защиты
  → slug `siz-ochki` (Очки и щитки защитные) | refs `tt-siz-ochki-shitok+tt-siz-ochki-zashchitnye`
  → analyst: **correct** — Защитный лицевой щиток — slug «Очки и щитки защитные» (щитки прямо в значении slug); same-slug multi = одна классификация. MONITORING.
- **36307** [MON: tt-siz-ochki-shitok] | Маска щиток защитный лицевой НБТ поликарбонат ЭКОН | art=РСВ-339084 | sg=Средства индивидуальной защиты
  → slug `siz-ochki` (Очки и щитки защитные) | refs `tt-siz-ochki-shitok+tt-siz-ochki-zashchitnye`
  → analyst: **correct** — Защитный лицевой щиток поликарбонат — slug «Очки и щитки защитные»; same-slug multi. MONITORING.
- **36310** [MON: tt-siz-ochki-shitok] | Маска щиток защитный лицевой СИБИН с экраном из поликарбоната | art=11089 | sg=Средства индивидуальной защиты
  → slug `siz-ochki` (Очки и щитки защитные) | refs `tt-siz-ochki-shitok+tt-siz-ochki-zashchitnye`
  → analyst: **correct** — Защитный лицевой щиток СИБИН — slug «Очки и щитки защитные»; same-slug multi. MONITORING.
- **43696** [MON: tt-svar-apparaty-truby] | Аппарат для сварки полипр.труб Candan СМ-01 SET WV | art=РСВ-238539 | sg=Электроинструмент
  → slug `svar-apparaty` (Сварочные аппараты, инверторы, плазморезы) | refs `tt-svar-apparaty-truby`
  → analyst: **correct** — Аппарат для сварки ПП-труб Candan — подтип сварочных аппаратов (правило 5) — slug «Сварочные аппараты, инверторы, плазморезы». MONITORING.
- **43699** [MON: tt-svar-apparaty-truby] | Аппарат для сварки полипр.труб CANDAN СМ-06 SET (20,25,32,40мм) (WV) 750+750 Watt | art=238537 | sg=Электроинструмент
  → slug `svar-apparaty` (Сварочные аппараты, инверторы, плазморезы) | refs `tt-svar-apparaty-truby`
  → analyst: **correct** — Аппарат для сварки ПП-труб CANDAN — slug «Сварочные аппараты». MONITORING.

## B. Строки, отмеченные analyst как borderline (рекомендовано к проверке)

- **31104** [BORDERLINE] | Регулятор расхода газа А-90-5 азотный 90л/мин 1,0М | art=ПТК-А905 | sg=Сварочное оборудование
  → slug `svar-reduktory` (Газовые редукторы) | refs `tt-svar-reduktory-regulyator`
  → analyst: **correct** — Регулятор расхода газа А-90-5 (азот, sg=Сварочное оборудование) — slug «Газовые редукторы»: потоковый регулятор, торгово объединяется с редукторами; v1-правило. BORDERLINE — рекомендовано к проверке reviewer.
  → примечание analyst: потоковый регулятор расхода газа (не понижающий редуктор) — проверить принадлежность к «Газовые редукторы»

## C. Spot-check analyst-correct (предложение: seed 20260722, 20 из 90 non-monitoring correct)

Reviewer может принять этот набор или запросить другой random-draw.

- **315** [SPOT] | Стяжка груза  6м (полипропилен) 35мм 2000 кг. | art=73720 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза полипропиленовая — slug «Тросы, канаты, такелаж».
- **326** [SPOT] | Стяжка груза 6м (полипропилен)  ТОЛЬЯТТИ | art=70000 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза — slug «Тросы, канаты, такелаж».
- **366** [SPOT] | Трос ленточный 10т СУПЕР УСИЛЕННЫЙ  5.0 м. 2 крюка | art=19010 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Трос ленточный усиленный 10т — slug «Тросы, канаты, такелаж».
- **677** [SPOT] | Фонарь аккум Einhell PXC TE-CL 18/2000 LiAC, 18В без АККУМ и ЗУ | art=4514114 | sg=Аккумуляторный инструмент
  → slug `fonari` (Фонари) | refs `tt-fonari-akkum`
  → analyst: **correct** — Аккумуляторный фонарь Einhell — slug «Фонари».
- **6215** [SPOT] | Шампунь для минимоек HUTER усиленный концентрат Super Power Foam 5,8кг | art=71/5/42 | sg=Герметики, пены, клеи и пр отделочные материалы
  → slug `obor-pena` (Пеногенераторы и автохимия) | refs `tt-obor-pena-shampun`
  → analyst: **correct** — Шампунь для минимоек = автохимия — slug «Пеногенераторы и автохимия»; прецедент 6213 (правило 24).
- **24867** [SPOT] | Припой ПОС 61, трубка с канифолью, 100г, 1мм | art=55450-100-10C | sg=Осветительное и электротехническое оборудование
  → slug `raskhodniki-pajki` (Расходники для пайки) | refs `tt-raskhodniki-pajki-pripoy`
  → analyst: **correct** — Припой ПОС-61 с канифолью — slug «Расходники для пайки».
- **28894** [SPOT] | Пневмонейлер ЗУБР для барабанных гвоздей 65-100мм | art=31915 | sg=Пневмоинструмент
  → slug `bp-pnevmosteplery` (Пневмостеплеры и нейлеры) | refs `tt-bp-pnevmosteplery-gvozde`
  → analyst: **correct** — Пневмонейлер ЗУБР — slug «Пневмостеплеры и нейлеры».
- **29035** [SPOT] | Регулятор давления RPF-187R с маном.диам 40мм, вхо | art=GAV-22923 | sg=Пневмоинструмент
  → slug `bp-podgotovka-vozduha` (Подготовка сжатого воздуха) | refs `tt-bp-podgotovka-vozduha-vlagootdelitel`
  → analyst: **correct** — Регулятор давления с манометром (пневмо) — slug «Подготовка сжатого воздуха» (правило 18).
- **37015** [SPOT] | Гвоздодер 400 мм, D-17 мм | art=41-0-240 | sg=Строительно-отделочный инструмент
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Гвоздодёр 400мм — slug «Ломы, гвоздодёры, монтировки».
- **37271** [SPOT] | Лента малярная креповая 30ммх50м ЗУБР ЭКСПЕРТ | art=12115-30 | sg=Строительно-отделочный инструмент
  → slug `hoz-lenty` (Ленты клейкие и сигнальные) | refs `tt-hoz-lenty-malyarnaya`
  → analyst: **correct** — Малярная креповая лента 30мм — slug «Ленты клейкие и сигнальные».
- **37272** [SPOT] | Лента малярная креповая 38ммх50м ЗУБР ЭКСПЕРТ | art=12115-38 | sg=Строительно-отделочный инструмент
  → slug `hoz-lenty` (Ленты клейкие и сигнальные) | refs `tt-hoz-lenty-malyarnaya`
  → analyst: **correct** — Малярная креповая лента 38мм — slug «Ленты клейкие и сигнальные».
- **37273** [SPOT] | Лента малярная креповая 48ммх50м ЗУБР ЭКСПЕРТ | art=12115-50 | sg=Строительно-отделочный инструмент
  → slug `hoz-lenty` (Ленты клейкие и сигнальные) | refs `tt-hoz-lenty-malyarnaya`
  → analyst: **correct** — Малярная креповая лента 48мм — slug «Ленты клейкие и сигнальные».
- **40678** [SPOT] | Лом строительный 1500мм 25 мм СИБИН | art=2182-15 | sg=Хозтовары, сад, огород
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Строительный лом 1500мм — slug «Ломы, гвоздодёры, монтировки».
- **43774** [SPOT] | Газонокосилка электрическая Einhell GE-EM 1233, 1250Вт, 33см, 30л | art=3400192 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка Einhell — slug «Газонокосилки».
- **43780** [SPOT] | Газонокосилка электрическая Hitachi EL340; 1200 Вт | art=HTC-EL340 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка Hitachi — slug «Газонокосилки».
- **43787** [SPOT] | Газонокосилка электрическая ЗУБР 2000Вт 42см | art=ГСЦ-42-2000 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка ЗУБР 2000Вт — slug «Газонокосилки».
- **44277** [SPOT] | Насос дренажный ДН-1100Н ВИХРЬ | art=68/2/5 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Дренажный насос ВИХРЬ — slug «Насосы».
- **44281** [SPOT] | Насос дренажный ДН-750 ВИХРЬ | art=68/2/2 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Дренажный насос ВИХРЬ — slug «Насосы».
- **44319** [SPOT] | Насос погружной Мини ГНОМ (ГНОМ 7-7) Подача 7 куб. | art=ГНМ-7700 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Погружной насос ГНОМ — slug «Насосы».
- **44340** [SPOT] | Насос фекальный ФН-1500Л | art=68/5/5 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Фекальный насос — slug «Насосы».

## D. Полная разметка (103 строки)

- **189** | Компрессор R17 Сервис Ключ | art=75572 | sg=Автомобильный инструмент
  → slug `bp-kompressory` (Компрессоры) | refs `tt-bp-kompressory-avto`
  → analyst: **correct** — Автомобильный компрессор (Сервис Ключ) — slug «Компрессоры»; правило 23: авто-компрессоры остаются компрессорами.
- **193** | Компрессор автомобильный DENZEL АС-75 12В, 10атм, 75л/мин | art=58051 | sg=Автомобильный инструмент
  → slug `bp-kompressory` (Компрессоры) | refs `tt-bp-kompressory-avto`
  → analyst: **correct** — Автомобильный компрессор 12В DENZEL — slug «Компрессоры».
- **197** | Компрессор поршневой автомобильный СПЕЦ КПА-35, 35 | art=СПЕЦ-3223 | sg=Автомобильный инструмент
  → slug `bp-kompressory` (Компрессоры) | refs `tt-bp-kompressory-avto`
  → analyst: **correct** — Поршневой автомобильный компрессор СПЕЦ — slug «Компрессоры».
- **304** | Стяжка груза   816кг 3,04мх2,54см САТ (4шт) | art=980093I | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза (такелажная, 4 шт) — slug «Тросы, канаты, такелаж»; двухсловный keyword правила 9 отделяет от стяжек пружин.
- **310** | Стяжка груза  1362кг 4,87мх3,17см САТ (4шт) | art=980096I | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза — slug «Тросы, канаты, такелаж».
- **313** | Стяжка груза  2043кг 4,87мх3,8см САТ (4шт) | art=980106I | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза — slug «Тросы, канаты, такелаж».
- **315** | Стяжка груза  6м (полипропилен) 35мм 2000 кг. | art=73720 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза полипропиленовая — slug «Тросы, канаты, такелаж».
- **320** | Стяжка груза 12м усил. крюк (полипропилен)  ТОЛЬЯТ | art=70003 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза усиленная — slug «Тросы, канаты, такелаж».
- **326** | Стяжка груза 6м (полипропилен)  ТОЛЬЯТТИ | art=70000 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Стяжка груза — slug «Тросы, канаты, такелаж».
- **363** | Трос ленточный  5т 2крюка | art=73705 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Трос ленточный (буксировочный) 5т — slug «Тросы, канаты, такелаж».
- **366** | Трос ленточный 10т СУПЕР УСИЛЕННЫЙ  5.0 м. 2 крюка | art=19010 | sg=Автомобильный инструмент
  → slug `krep-takelazh` (Тросы, канаты, такелаж) | refs `tt-krep-takelazh-styazhka`
  → analyst: **correct** — Трос ленточный усиленный 10т — slug «Тросы, канаты, такелаж».
- **422** [MON: tt-bp-vozdukhoduvki-akkum] [AMENDMENT] | Воздуходувка аккум DENZEL RB180-36, Li-ion 36В 4Ач, 180км/ч 820м3/ч 2 аккум 18В 4Ач | art=59610 | sg=Аккумуляторный инструмент
  → slug `bp-vozdukhoduvki` (Воздуходувки) | refs `tt-bp-vozdukhoduvki-akkum`
  → analyst: **correct** — Аккумуляторная воздуходувка — slug «Воздуходувки»; тип не зависит от источника питания (review правила 8). MONITORING.
- **429** | Газонокосилка аккумуляторная  ЗУБР ГКЛ-3736-42, 37см бесщеточ 36В, 2х18В АКБ 4ач | art=ГКЛ-3736-42 | sg=Аккумуляторный инструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Аккумуляторная газонокосилка — slug «Газонокосилки».
- **665** | Фонарь BOSCH GLI (без аккум.и зар.устройства) | art=BSH-06014A0000 | sg=Аккумуляторный инструмент
  → slug `fonari` (Фонари) | refs `tt-fonari-akkum`
  → analyst: **correct** — Аккумуляторный фонарь BOSCH — slug «Фонари».
- **673** | Фонарь Hitachi UB18D, 14,4 - 18V, (аккумулятора, з | art=HTC-UB18D | sg=Аккумуляторный инструмент
  → slug `fonari` (Фонари) | refs `tt-fonari-akkum`
  → analyst: **correct** — Аккумуляторный фонарь Hitachi — slug «Фонари».
- **677** | Фонарь аккум Einhell PXC TE-CL 18/2000 LiAC, 18В без АККУМ и ЗУ | art=4514114 | sg=Аккумуляторный инструмент
  → slug `fonari` (Фонари) | refs `tt-fonari-akkum`
  → analyst: **correct** — Аккумуляторный фонарь Einhell — slug «Фонари».
- **1113** | Адаптер-переходник для инструмента MAKITA с аккум DEWALT | art=40309-MD | sg=Аккумуляторы и зарядные устройства
  → slug `adaptery` (Адаптеры и переходники) | refs `tt-adaptery-universal`
  → analyst: **correct** — Адаптер АКБ-платформ (DeWalt→Makita) — slug «Адаптеры и переходники».
- **1818** | Свеча зажигания для 2- такт CMR7H MD-STARS | art=CMR7H | sg=Бензоинструмент и расходники для них
  → slug `zap-svechi` (Свечи зажигания) | refs `tt-zap-svechi-zazhiganiya`
  → analyst: **correct** — Свеча зажигания для 2-тактных двигателей — slug «Свечи зажигания».
- **1857** [MON: tt-yashchiki-sumki-benzopila] | Сумка для бензопилы тем.сер+оранж | art=OZONE R-7125 | sg=Бензоинструмент и расходники для них
  → slug `yashchiki-sumki` (Ящики, сумки, органайзеры) | refs `tt-yashchiki-sumki-benzopila`
  → analyst: **correct** — Сумка для бензопилы — slug «Ящики, сумки, органайзеры». MONITORING (правило 20).
- **1858** [MON: tt-yashchiki-sumki-benzopila] | Сумка для бензопилы темно-синий | art=OZONE R-5112 | sg=Бензоинструмент и расходники для них
  → slug `yashchiki-sumki` (Ящики, сумки, органайзеры) | refs `tt-yashchiki-sumki-benzopila`
  → analyst: **correct** — Сумка для бензопилы — slug «Ящики, сумки, органайзеры». MONITORING (правило 20).
- **6215** | Шампунь для минимоек HUTER усиленный концентрат Super Power Foam 5,8кг | art=71/5/42 | sg=Герметики, пены, клеи и пр отделочные материалы
  → slug `obor-pena` (Пеногенераторы и автохимия) | refs `tt-obor-pena-shampun`
  → analyst: **correct** — Шампунь для минимоек = автохимия — slug «Пеногенераторы и автохимия»; прецедент 6213 (правило 24).
- **6683** | Адаптер для подключения пылесоса резиновый 32/35/38/41мм ПУЛЬСАР | art=792-131 | sg=Запасные части
  → slug `adaptery` (Адаптеры и переходники) | refs `tt-adaptery-universal`
  → analyst: **correct** — Резиновый адаптер шланга пылесоса 32–41мм — slug «Адаптеры и переходники».
- **10633** | Держатель с микролифтом KRAFTOOL MM1 | art=34706 | sg=Измерительный инструмент
  → slug `izm-shtativy` (Штативы, отражатели, держатели) | refs `tt-izm-shtativy-derzhatel`
  → analyst: **correct** — Держатель с микролифтом (измерительный) — slug «Штативы, отражатели, держатели» (держатели прямо в значении slug).
- **10807** [MON: tt-izm-kolesa-dorozhnoe] | Колесо дорожное BOSCH GWM 32, 10000м, 0.5 мм/м, Диаметр колеса 31.9 см, Вес 2 кг | art=0601074000 | sg=Измерительный инструмент
  → slug `izm-kolesa` (Измерительные колёса (курвиметры)) | refs `tt-izm-kolesa-dorozhnoe`
  → analyst: **correct** — Дорожное измерительное колесо BOSCH — slug «Измерительные колёса (курвиметры)». MONITORING (правило 17).
- **12944** | Ключ динамометрический  1/2" (28-210Nm)  465мм  JTC | art=JTC-1203 | sg=Ключи, головки, воротки, удлинители
  → slug `dinamometricheskie-klyuchi` (Динамометрические ключи) | refs `tt-dinamometricheskie-klyuchi-klyuch`
  → analyst: **correct** — Динамометрический ключ 1/2" — slug «Динамометрические ключи».
- **12955** | Ключ динамометрический  1/4", 6 - 30 Нм,с кольцевым фиксатором, ЗУБР | art=64081-030 | sg=Ключи, головки, воротки, удлинители
  → slug `dinamometricheskie-klyuchi` (Динамометрические ключи) | refs `tt-dinamometricheskie-klyuchi-klyuch`
  → analyst: **correct** — Динамометрический ключ 1/4" — slug «Динамометрические ключи».
- **12980** | Ключ динамометрический 1/4", 5-25 Нм, KING TONY | art=34223-1А | sg=Ключи, головки, воротки, удлинители
  → slug `dinamometricheskie-klyuchi` (Динамометрические ключи) | refs `tt-dinamometricheskie-klyuchi-klyuch`
  → analyst: **correct** — Динамометрический ключ 1/4" KING TONY — slug «Динамометрические ключи».
- **13002** | Ключ динамометрический, 1/2", 28 - 210 Нм, ЗУБР Профессионал | art=64094-210 | sg=Ключи, головки, воротки, удлинители
  → slug `dinamometricheskie-klyuchi` (Динамометрические ключи) | refs `tt-dinamometricheskie-klyuchi-klyuch`
  → analyst: **correct** — Динамометрический ключ 1/2" ЗУБР — slug «Динамометрические ключи».
- **22670** | Набор звездочек TORX с отверстием на конце (9 пр.) PROFFI | art=76435 | sg=Наборы инструмента
  → slug `nabory-instrumenta` (Наборы инструмента) | refs `tt-nabory-instrumenta-zvezdochki`
  → analyst: **correct** — Набор торкс-звёздочек (9 пр.) — slug «Наборы инструмента».
- **22672** | Набор звездочек СЕРВИС КЛЮЧ (торкс) с отверстием на конце Т10-Т50 9 предметов | art=70675 | sg=Наборы инструмента
  → slug `nabory-instrumenta` (Наборы инструмента) | refs `tt-nabory-instrumenta-zvezdochki`
  → analyst: **correct** — Набор торкс-звёздочек Т10–Т50 — slug «Наборы инструмента».
- **22677** | Набор звездочек СЕРВИС КЛЮЧ 1/2+1/4 Е4-Е24 14пр | art=76605 | sg=Наборы инструмента
  → slug `nabory-instrumenta` (Наборы инструмента) | refs `tt-nabory-instrumenta-zvezdochki`
  → analyst: **correct** — Набор звёздочек E4–E24 — slug «Наборы инструмента».
- **24724** | Паяльник 100Вт, клин, STAYER | art=55300-100 | sg=Осветительное и электротехническое оборудование
  → slug `payalniki` (Паяльники) | refs `tt-payalniki-elektro`
  → analyst: **correct** — Электропаяльник 100Вт — slug «Паяльники» (payalniki, не станции — правило 14).
- **24733** | Паяльник 30-130Вт, пист рукояткой | art=55317-130 | sg=Осветительное и электротехническое оборудование
  → slug `payalniki` (Паяльники) | refs `tt-payalniki-elektro`
  → analyst: **correct** — Электропаяльник 30–130Вт — slug «Паяльники».
- **24740** | Паяльник 40 Вт, дер.ручка, долговеч.жало ЗУБР МАСТ | art=55405-40_z01 | sg=Осветительное и электротехническое оборудование
  → slug `payalniki` (Паяльники) | refs `tt-payalniki-elektro`
  → analyst: **correct** — Электропаяльник 40Вт ЗУБР — slug «Паяльники».
- **24855** | Припой оловянно-свинцовый 30% Sn/70% Pb 250 гр. СВ | art=SV-55325-250 | sg=Осветительное и электротехническое оборудование
  → slug `raskhodniki-pajki` (Расходники для пайки) | refs `tt-raskhodniki-pajki-pripoy`
  → analyst: **correct** — Припой оловянно-свинцовый — slug «Расходники для пайки».
- **24867** | Припой ПОС 61, трубка с канифолью, 100г, 1мм | art=55450-100-10C | sg=Осветительное и электротехническое оборудование
  → slug `raskhodniki-pajki` (Расходники для пайки) | refs `tt-raskhodniki-pajki-pripoy`
  → analyst: **correct** — Припой ПОС-61 с канифолью — slug «Расходники для пайки».
- **24874** | Припой ПОС-61, трубка с канифолью, 100 г.,0,8мм | art=55450-100-08С | sg=Осветительное и электротехническое оборудование
  → slug `raskhodniki-pajki` (Расходники для пайки) | refs `tt-raskhodniki-pajki-pripoy`
  → analyst: **correct** — Припой ПОС-61 — slug «Расходники для пайки».
- **27253** | Провода стартовые 3,0 м. 500 Ампер | art=73114 | sg=Оснастка
  → slug `puskovye-provoda` (Пусковые провода) | refs `tt-puskovye-provoda-startovye`
  → analyst: **correct** — Стартовые (пусковые) провода 500А — slug «Пусковые провода».
- **28890** | Пневмонейлер RAPID ЗЬЗ171(гвоздезабиватель) для гвоздей тип 23P 15-35мм | art=5001345 | sg=Пневмоинструмент
  → slug `bp-pnevmosteplery` (Пневмостеплеры и нейлеры) | refs `tt-bp-pnevmosteplery-gvozde`
  → analyst: **correct** — Пневмонейлер (гвозди 23P) — slug «Пневмостеплеры и нейлеры» (нейлер прямо в значении slug).
- **28894** | Пневмонейлер ЗУБР для барабанных гвоздей 65-100мм | art=31915 | sg=Пневмоинструмент
  → slug `bp-pnevmosteplery` (Пневмостеплеры и нейлеры) | refs `tt-bp-pnevmosteplery-gvozde`
  → analyst: **correct** — Пневмонейлер ЗУБР — slug «Пневмостеплеры и нейлеры».
- **29035** | Регулятор давления RPF-187R с маном.диам 40мм, вхо | art=GAV-22923 | sg=Пневмоинструмент
  → slug `bp-podgotovka-vozduha` (Подготовка сжатого воздуха) | refs `tt-bp-podgotovka-vozduha-vlagootdelitel`
  → analyst: **correct** — Регулятор давления с манометром (пневмо) — slug «Подготовка сжатого воздуха» (правило 18).
- **29557** [MON: tt-siz-izveshchateli-gromkogovoritel] [AMENDMENT] | Громкоговоритель HS-10-A (INTER-M) рупорный 10Вт | art=216632 | sg=Пожарка
  → slug `siz-izveshchateli` (Извещатели и оповещатели) | refs `tt-siz-izveshchateli-gromkogovoritel`
  → analyst: **correct** — Рупорный громкоговоритель 10Вт (sg=Пожарка) — slug «Извещатели и оповещатели»: оповещатель по значению slug; MONITORING (правило 26), прецедентов наполнения slug нет — обязательная проверка reviewer.
- **29733** [MON: tt-siz-pozh-inventar-polotno] [AMENDMENT] | Полотно противопожарное ПП-1000 (1,5*2,0) (до 1000 | art=ОГН-ПП1000 | sg=Пожарка
  → slug `siz-pozh-inventar` (Пожарный инвентарь) | refs `tt-siz-pozh-inventar-polotno`
  → analyst: **correct** — Противопожарное полотно ПП-1000 — slug «Пожарный инвентарь». MONITORING (правило 22).
- **30216** | Кейс HIKOKI HSC II пустой 157,5х400х300мм | art=402545 | sg=Прочее
  → slug `yashchiki-sumki` (Ящики, сумки, органайзеры) | refs `tt-yashchiki-sumki-keys-prochee`
  → analyst: **correct** — Инструментальный кейс HIKOKI — slug «Ящики, сумки, органайзеры».
- **30229** | Кейс пластиковый Hitachi (пила) | art=321188 | sg=Прочее
  → slug `yashchiki-sumki` (Ящики, сумки, органайзеры) | refs `tt-yashchiki-sumki-keys-prochee`
  → analyst: **correct** — Пластиковый кейс Hitachi — slug «Ящики, сумки, органайзеры».
- **31104** | Регулятор расхода газа А-90-5 азотный 90л/мин 1,0М | art=ПТК-А905 | sg=Сварочное оборудование
  → slug `svar-reduktory` (Газовые редукторы) | refs `tt-svar-reduktory-regulyator`
  → analyst: **correct** — Регулятор расхода газа А-90-5 (азот, sg=Сварочное оборудование) — slug «Газовые редукторы»: потоковый регулятор, торгово объединяется с редукторами; v1-правило. BORDERLINE — рекомендовано к проверке reviewer.
- **31973** [MON: tt-obor-mebel-verstak] | Верстак Bosch PTA 1000 для PCM7; высота 700-1150мм | art=BSH-0603B05100 | sg=Слесарно-столярный инструмент
  → slug `obor-mebel` (Верстаки и мебель мастерской) | refs `tt-obor-mebel-verstak`
  → analyst: **correct** — Верстак Bosch PTA 1000 — slug «Верстаки и мебель мастерской». MONITORING (правило 13).
- **31974** [MON: tt-obor-mebel-verstak] | Верстак Bosch PTA 2400 для PCM8S; высота 800мм, дл | art=BSH-0603B05000 | sg=Слесарно-столярный инструмент
  → slug `obor-mebel` (Верстаки и мебель мастерской) | refs `tt-obor-mebel-verstak`
  → analyst: **correct** — Верстак Bosch PTA 2400 — slug «Верстаки и мебель мастерской». MONITORING (правило 13).
- **34648** | Стержни клеевые 12х300 мм., прозрачные универс. ЗУ | art=06856-12-1 | sg=Слесарно-столярный инструмент
  → slug `sterzhni-kleevye` (Клеевые стержни) | refs `tt-sterzhni-kleevye-kleevye`
  → analyst: **correct** — Клеевые стержни 12мм — slug «Клеевые стержни».
- **34649** | Стержни клеевые 12х300 мм., цвет желтый, сверхсиль | art=06856-12-2 | sg=Слесарно-столярный инструмент
  → slug `sterzhni-kleevye` (Клеевые стержни) | refs `tt-sterzhni-kleevye-kleevye`
  → analyst: **correct** — Клеевые стержни 12мм — slug «Клеевые стержни».
- **34656** | Стержни клеевые 8х200мм прозрачные, универсальные, | art=06855-08-1 | sg=Слесарно-столярный инструмент
  → slug `sterzhni-kleevye` (Клеевые стержни) | refs `tt-sterzhni-kleevye-kleevye`
  → analyst: **correct** — Клеевые стержни 8мм — slug «Клеевые стержни».
- **34658** | Стержни клеевые д.8 мм за 12 шт. | art=FIT-14408 | sg=Слесарно-столярный инструмент
  → slug `sterzhni-kleevye` (Клеевые стержни) | refs `tt-sterzhni-kleevye-kleevye`
  → analyst: **correct** — Клеевые стержни 8мм — slug «Клеевые стержни».
- **35061** | Тонконосы 160 мм Серия Люкс Профи прорезиненная ру | art=FIT-50736 | sg=Слесарно-столярный инструмент
  → slug `passatizhi` (Пассатижи и плоскогубцы) | refs `tt-passatizhi-tonkonosy`
  → analyst: **correct** — Тонконосы 160мм — подтип плоскогубцев (правило 12) — slug «Пассатижи и плоскогубцы».
- **35062** | Тонконосы 165мм Серия ЭЛЕКТРО | art=FIT-50786 | sg=Слесарно-столярный инструмент
  → slug `passatizhi` (Пассатижи и плоскогубцы) | refs `tt-passatizhi-tonkonosy`
  → analyst: **correct** — Тонконосы 165мм — slug «Пассатижи и плоскогубцы».
- **36140** | Кобура для шуруповерта с отделениями для бит и сверл ЗУБР | art=38630 | sg=Средства индивидуальной защиты
  → slug `kobury-dlya-instrumenta` (Кобуры для инструмента) | refs `tt-kobury-dlya-instrumenta-kobura`
  → analyst: **correct** — Кобура для шуруповёрта — slug «Кобуры для инструмента»; sg=СИЗ — особенность каталога, не ошибка правила.
- **36301** [MON: tt-siz-ochki-shitok] | Маска щиток защитный лицевой ЕВРО закрытый НБТ-2 | art=РСВ-64445 | sg=Средства индивидуальной защиты
  → slug `siz-ochki` (Очки и щитки защитные) | refs `tt-siz-ochki-shitok+tt-siz-ochki-zashchitnye`
  → analyst: **correct** — Защитный лицевой щиток — slug «Очки и щитки защитные» (щитки прямо в значении slug); same-slug multi = одна классификация. MONITORING.
- **36307** [MON: tt-siz-ochki-shitok] | Маска щиток защитный лицевой НБТ поликарбонат ЭКОН | art=РСВ-339084 | sg=Средства индивидуальной защиты
  → slug `siz-ochki` (Очки и щитки защитные) | refs `tt-siz-ochki-shitok+tt-siz-ochki-zashchitnye`
  → analyst: **correct** — Защитный лицевой щиток поликарбонат — slug «Очки и щитки защитные»; same-slug multi. MONITORING.
- **36310** [MON: tt-siz-ochki-shitok] | Маска щиток защитный лицевой СИБИН с экраном из поликарбоната | art=11089 | sg=Средства индивидуальной защиты
  → slug `siz-ochki` (Очки и щитки защитные) | refs `tt-siz-ochki-shitok+tt-siz-ochki-zashchitnye`
  → analyst: **correct** — Защитный лицевой щиток СИБИН — slug «Очки и щитки защитные»; same-slug multi. MONITORING.
- **37015** | Гвоздодер 400 мм, D-17 мм | art=41-0-240 | sg=Строительно-отделочный инструмент
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Гвоздодёр 400мм — slug «Ломы, гвоздодёры, монтировки».
- **37017** | Гвоздодер 800 мм,D-17 мм, армированный | art=41-5-080 | sg=Строительно-отделочный инструмент
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Гвоздодёр 800мм армированный — slug «Ломы, гвоздодёры, монтировки».
- **37019** | Гвоздодер металлический  45 см TRUPER | art=10853 | sg=Строительно-отделочный инструмент
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Гвоздодёр TRUPER 45см — slug «Ломы, гвоздодёры, монтировки».
- **37020** | Гвоздодер металлический  60 см TRUPER | art=10856 | sg=Строительно-отделочный инструмент
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Гвоздодёр TRUPER 60см — slug «Ломы, гвоздодёры, монтировки».
- **37271** | Лента малярная креповая 30ммх50м ЗУБР ЭКСПЕРТ | art=12115-30 | sg=Строительно-отделочный инструмент
  → slug `hoz-lenty` (Ленты клейкие и сигнальные) | refs `tt-hoz-lenty-malyarnaya`
  → analyst: **correct** — Малярная креповая лента 30мм — slug «Ленты клейкие и сигнальные».
- **37272** | Лента малярная креповая 38ммх50м ЗУБР ЭКСПЕРТ | art=12115-38 | sg=Строительно-отделочный инструмент
  → slug `hoz-lenty` (Ленты клейкие и сигнальные) | refs `tt-hoz-lenty-malyarnaya`
  → analyst: **correct** — Малярная креповая лента 38мм — slug «Ленты клейкие и сигнальные».
- **37273** | Лента малярная креповая 48ммх50м ЗУБР ЭКСПЕРТ | art=12115-50 | sg=Строительно-отделочный инструмент
  → slug `hoz-lenty` (Ленты клейкие и сигнальные) | refs `tt-hoz-lenty-malyarnaya`
  → analyst: **correct** — Малярная креповая лента 48мм — slug «Ленты клейкие и сигнальные».
- **39790** | Изолента 15ммх10м БЕЛАЯ СИБРТЕХ | art=88792 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента 15мм ПВХ — slug «Изолента».
- **39791** | Изолента 15ммх10м ЖЕЛТАЯ СИБРТЕХ | art=88790 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента 15мм ПВХ — slug «Изолента».
- **39826** | Изолента ПВХ 15мм зелен (10м) не поддерж горение, | art=1233-4_z01 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента ПВХ не поддерживающая горение — slug «Изолента».
- **39828** | Изолента ПВХ 15мм синий (10м) ВИХРЬ | art=73/3/3/2 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента ПВХ ВИХРЬ — slug «Изолента».
- **39833** | Изолента ПВХ 15ммх20м белая | art=098205 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента ПВХ 20м — slug «Изолента».
- **39837** | Изолента ПВХ 19мм желтая (20м) | art=064379 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента ПВХ 19мм — slug «Изолента».
- **39841** | Изолента ПВХ 19мм синий (20м) ВИХРЬ | art=73/3/3/4 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента ПВХ ВИХРЬ — slug «Изолента».
- **39848** | Изолента ПВХ 19мм х 20м синяя ЗУБР Электрик-20 не поддерживающая горение, 6000 В | art=1234-7 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента ЗУБР Электрик 6000В — slug «Изолента».
- **39874** | Изолента х/б прорезиненная черная 200г (90)  БИБЕР | art=92012 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента х/б прорезиненная — slug «Изолента».
- **39883** | Изолента хб черная, 70г. | art=49-5-100 | sg=Хозтовары, сад, огород
  → slug `hoz-izolenta` (Изолента) | refs `tt-hoz-izolenta-izolenta`
  → analyst: **correct** — Изолента х/б — slug «Изолента».
- **40678** | Лом строительный 1500мм 25 мм СИБИН | art=2182-15 | sg=Хозтовары, сад, огород
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Строительный лом 1500мм — slug «Ломы, гвоздодёры, монтировки».
- **40683** | Лом строительный диам. 25мм длина 1250-1300мм | art=ЛС-25-1300 | sg=Хозтовары, сад, огород
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Строительный лом 1250–1300мм — slug «Ломы, гвоздодёры, монтировки».
- **40684** | Лом строительный диам. 25мм длина 1350мм | art=РСВ-36131 | sg=Хозтовары, сад, огород
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Строительный лом 1350мм — slug «Ломы, гвоздодёры, монтировки».
- **40685** | Лом строительный диам. 28мм длина 1250-1300мм | art=ЛС-28-1300 | sg=Хозтовары, сад, огород
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Строительный лом 28мм — slug «Ломы, гвоздодёры, монтировки».
- **40686** | Лом строительный диам. 30мм длина 1250мм Сибртех | art=253245 | sg=Хозтовары, сад, огород
  → slug `lomy-gvozdodery` (Ломы, гвоздодёры, монтировки) | refs `tt-lomy-gvozdodery-lom`
  → analyst: **correct** — Строительный лом 30мм Сибртех — slug «Ломы, гвоздодёры, монтировки».
- **43696** [MON: tt-svar-apparaty-truby] | Аппарат для сварки полипр.труб Candan СМ-01 SET WV | art=РСВ-238539 | sg=Электроинструмент
  → slug `svar-apparaty` (Сварочные аппараты, инверторы, плазморезы) | refs `tt-svar-apparaty-truby`
  → analyst: **correct** — Аппарат для сварки ПП-труб Candan — подтип сварочных аппаратов (правило 5) — slug «Сварочные аппараты, инверторы, плазморезы». MONITORING.
- **43699** [MON: tt-svar-apparaty-truby] | Аппарат для сварки полипр.труб CANDAN СМ-06 SET (20,25,32,40мм) (WV) 750+750 Watt | art=238537 | sg=Электроинструмент
  → slug `svar-apparaty` (Сварочные аппараты, инверторы, плазморезы) | refs `tt-svar-apparaty-truby`
  → analyst: **correct** — Аппарат для сварки ПП-труб CANDAN — slug «Сварочные аппараты». MONITORING.
- **43768** | Газонокосилка LM5131 CHAMPION 3кВт травосбоник 60л | art=РСВ-251847 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка CHAMPION 3кВт — slug «Газонокосилки».
- **43774** | Газонокосилка электрическая Einhell GE-EM 1233, 1250Вт, 33см, 30л | art=3400192 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка Einhell — slug «Газонокосилки».
- **43775** | Газонокосилка электрическая ELM-1800Р Huter пластик кожух | art=70/4/7 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка Huter — slug «Газонокосилки».
- **43780** | Газонокосилка электрическая Hitachi EL340; 1200 Вт | art=HTC-EL340 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка Hitachi — slug «Газонокосилки».
- **43786** | Газонокосилка электрическая ЗУБР 1700Вт 38см | art=СГЦ-38-1700 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка ЗУБР 1700Вт — slug «Газонокосилки».
- **43787** | Газонокосилка электрическая ЗУБР 2000Вт 42см | art=ГСЦ-42-2000 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Электрическая газонокосилка ЗУБР 2000Вт — slug «Газонокосилки».
- **43789** | Газонокосилка электрическая ЗУБР роторная, 42 см, | art=ЗГКЭ-42-1800 | sg=Электроинструмент
  → slug `bp-gazonokosilki` (Газонокосилки) | refs `tt-bp-gazonokosilki-gazonokosilka`
  → analyst: **correct** — Роторная газонокосилка ЗУБР — slug «Газонокосилки».
- **44222** | Насос вибрационный ВН-15Н Вихрь, 15 м кабель, ниж. | art=68/8/6 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Вибрационный насос Вихрь — slug «Насосы» (правило 3: электрические насосы → obor-nasosy).
- **44223** | Насос вибрационный ВН-25В Вихрь, 25 м кабель, верх | art=68/8/3 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Вибрационный насос Вихрь — slug «Насосы».
- **44272** | Насос дренажный для грязной воды 400 Вт Зубр | art=НПГ-М1-400 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Дренажный насос Зубр — slug «Насосы».
- **44277** | Насос дренажный ДН-1100Н ВИХРЬ | art=68/2/5 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Дренажный насос ВИХРЬ — slug «Насосы».
- **44281** | Насос дренажный ДН-750 ВИХРЬ | art=68/2/2 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Дренажный насос ВИХРЬ — slug «Насосы».
- **44285** | Насос дренажный с минимальным уровнем откачки 550Вт ЗУБР АкваСенсор | art=НПЧ-Т7-550 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Дренажный насос ЗУБР АкваСенсор — slug «Насосы».
- **44307** | Насос поверхностный Джамбо 60/35Н | art=РСВ-119885 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Поверхностный насос Джамбо — slug «Насосы».
- **44312** | Насос поверхностный ПН-1100Н вихрь | art=68/4/3 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Поверхностный насос Вихрь — slug «Насосы».
- **44319** | Насос погружной Мини ГНОМ (ГНОМ 7-7) Подача 7 куб. | art=ГНМ-7700 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Погружной насос ГНОМ — slug «Насосы».
- **44332** | Насос скважинный СН-60/25 | art=68/3/14 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Скважинный насос — slug «Насосы».
- **44337** | Насос фекальный ФН-1050ЛЧ ВИХРЬ чугун | art=68/5/21 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Фекальный насос ВИХРЬ — slug «Насосы».
- **44338** | Насос фекальный ФН-1100Л ВИХРЬ | art=68/5/4 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Фекальный насос ВИХРЬ — slug «Насосы».
- **44339** | Насос фекальный ФН-1300ЛЧ ВИХРЬ чугун | art=68/5/22 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Фекальный насос ВИХРЬ — slug «Насосы».
- **44340** | Насос фекальный ФН-1500Л | art=68/5/5 | sg=Электроинструмент
  → slug `obor-nasosy` (Насосы) | refs `tt-obor-nasosy-nasos`
  → analyst: **correct** — Фекальный насос — slug «Насосы».
