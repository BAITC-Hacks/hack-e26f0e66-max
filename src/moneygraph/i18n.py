"""Interface translations: Russian, Kazakh, English.

Russian is the default: the analyst this tool is built for works in a
Kazakhstani bank. English and Kazakh are first-class options, not
afterthoughts. The code, the config and the exported CSVs stay in English,
because the jury checks that schema mechanically.

The Kazakh strings are machine translated and unreviewed. `MACHINE_TRANSLATED`
marks that, the interface shows a banner whenever Kazakh is selected, and
README.kk.md carries the same warning at the top. Presenting an unchecked
translation as finished work would be the actual mistake.

Two things are translated, and they are translated differently:

* **Interface text** — headings, explanations, labels. Plain dictionary lookup.
* **Evidence sentences** — regenerated per language from the node's `RuleTrace`,
  which holds the role, the gate and the numbers as *data*. Nothing is machine
  translated at runtime and no model is involved: the same structured facts are
  poured into a different template. That also means the language of the
  interface can never disagree with the numbers, because both come from the
  same trace.

The exported CSVs stay in English: their schema is checked mechanically by the
jury and the forbidden-word list is defined in English.

"""

from __future__ import annotations

# Order is the order shown in the language switcher, default first. Russian
# leads because the analyst this is built for works in a Kazakhstani bank; the
# code, the config and the exported CSVs stay in English.
LANGUAGES = {"ru": "Русский", "en": "English", "kk": "Қазақша"}
DEFAULT_LANG = "ru"

# The Kazakh strings were produced by machine translation and have not been
# reviewed by a native speaker. That is disclosed in the interface itself
# whenever Kazakh is selected, and at the top of README.kk.md — a translation
# nobody has checked should say so rather than be presented as authoritative.
MACHINE_TRANSLATED = {"kk"}

# ---------------------------------------------------------------------------
# roles
# ---------------------------------------------------------------------------

ROLE_NAMES = {
    "coordinator":  {"ru": "координатор", "kk": "үйлестіруші", "en": "coordinator"},
    "consolidator": {"ru": "точка сбора", "kk": "жинау нүктесі", "en": "consolidator"},
    "distributor":  {"ru": "распределитель", "kk": "таратушы", "en": "distributor"},
    "transit":      {"ru": "транзит", "kk": "транзит", "en": "transit"},
    "terminal":     {"ru": "конечный получатель", "kk": "соңғы алушы", "en": "terminal"},
    "cutoff":       {"ru": "обрыв обхода", "kk": "шолу шегі", "en": "cutoff"},
    "peripheral":   {"ru": "периферия", "kk": "перифериялық", "en": "peripheral"},
}

ROLE_MEANING = {
    "coordinator": {
        "ru": "Собирает средства с других точек сбора — кандидат на верхний уровень",
        "kk": "Басқа жинау нүктелерінен қаражат жинайды — жоғарғы деңгей үміткері",
        "en": "Collects from other collection points — candidate upper level"},
    "consolidator": {
        "ru": "Деньги от многих разных плательщиков сходятся сюда",
        "kk": "Көптеген әртүрлі төлеушілердің ақшасы осында жинақталады",
        "en": "Money from many separate payers converges here"},
    "distributor": {
        "ru": "Веерно рассылает деньги многим получателям",
        "kk": "Ақшаны көптеген алушыға желпуіш тәрізді таратады",
        "en": "Fans money out to many recipients"},
    "transit": {
        "ru": "Деньги приходят и идут дальше: вход примерно равен выходу",
        "kk": "Ақша келіп, әрі қарай кетеді: кіріс шығысқа шамалас",
        "en": "Money arrives and moves on, roughly in equals out"},
    "terminal": {
        "ru": "Деньги пришли и остались (исходящие переводы были прослежены)",
        "kk": "Ақша келіп, қалды (шығыс аударымдар тексерілген)",
        "en": "Money arrives and stays (outflow was traced)"},
    "cutoff": {
        "ru": "Дальнейшее движение не прослеживалось — выгрузка закончилась здесь",
        "kk": "Әрі қарайғы қозғалыс тексерілмеген — шолу осында аяқталды",
        "en": "Onward flow was never traced — the export stopped here"},
    "peripheral": {
        "ru": "Признаков роли не обнаружено",
        "kk": "Рөл белгілері анықталмады",
        "en": "No role indicators detected"},
}

# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------

UI: dict[str, dict[str, str]] = {
    # ---- tabs
    "tab.start":    {"ru": "Начало", "kk": "Бастау", "en": "Start here"},
    "tab.priority": {"ru": "Кого проверять первым",
                     "kk": "Алдымен кімді тексеру",
                     "en": "Who to review first"},
    "tab.account":  {"ru": "Карточка счёта", "kk": "Шот картасы",
                     "en": "Account detail"},
    "tab.groups":   {"ru": "Группы", "kk": "Топтар", "en": "Groups"},
    "tab.ask":      {"ru": "Спросить", "kk": "Сұрау", "en": "Ask"},
    "tab.agents":   {"ru": "Как принято решение", "kk": "Шешім қалай қабылданды",
                     "en": "How it decided"},
    "tab.data":     {"ru": "Ваши данные", "kk": "Сіздің деректеріңіз",
                     "en": "Your data"},
    "tab.cost":     {"ru": "Время и стоимость", "kk": "Уақыт және құны",
                     "en": "Cost & timing"},
    "tab.downloads": {"ru": "Выгрузки", "kk": "Жүктеп алу", "en": "Downloads"},

    # ---- start
    "start.title": {"ru": "Граф денег", "kk": "Ақша графы", "en": "Money Graph"},
    "start.lead": {
        "ru": "Правоохранительные органы передали банку 81 клиента, получавшего "
              "деньги от наркоторговли. Инструмент прошёл по их исходящим "
              "переводам четыре колена и восстановил, <b>кто стоит над ними</b>, "
              "затем проранжировал все счета по тому, насколько их стоит "
              "проверять, с письменным обоснованием для каждого.<br><br>"
              "<b>Всё здесь — гипотезы для проверки аналитиком, а не "
              "утверждения о факте.</b>",
        "kk": "Құқық қорғау органдары банкке есірткі саудасынан ақша алған "
              "81 клиентті берді. Құрал олардың шығыс аударымдары бойынша төрт "
              "буын жүріп өтіп, <b>олардың үстінде кім тұрғанын</b> қалпына "
              "келтірді, содан кейін барлық шоттарды тексеру маңыздылығы "
              "бойынша сұрыптап, әрқайсысына жазбаша негіздеме берді.<br><br>"
              "<b>Мұндағының бәрі — талдаушы тексеретін болжамдар, дәлелденген "
              "факт емес.</b>",
        "en": "Law enforcement gave the bank 81 customers known to have received "
              "drug-trafficking money. This tool followed their outgoing "
              "transfers four hops through the bank and worked out <b>who sits "
              "above them</b> — then ranked every account by how much it is "
              "worth reviewing, with a written reason for each.<br><br>"
              "<b>Everything here is a hypothesis for an analyst to verify, not "
              "a finding of fact.</b>"},

    "kpi.accounts": {"ru": "счетов в графе", "kk": "графтағы шот",
                     "en": "accounts traced"},
    "kpi.accounts.sub": {"ru": "от 81 известного клиента",
                         "kk": "81 белгілі клиенттен", "en": "from 81 known seeds"},
    "kpi.shortlist": {"ru": "в списке на проверку", "kk": "тексеру тізімінде",
                      "en": "to review first"},
    "kpi.shortlist.sub": {"ru": "с обоснованием", "kk": "негіздемесімен",
                          "en": "ranked, with reasons"},
    "kpi.turnover": {"ru": "тенге прослежено", "kk": "теңге тексерілді",
                     "en": "KZT traced"},
    "kpi.turnover.sub": {"ru": "июль 2026", "kk": "2026 шілде", "en": "July 2026"},
    "kpi.groups": {"ru": "найдено групп", "kk": "табылған топтар",
                   "en": "groups found"},
    "kpi.groups.sub": {"ru": "у каждой своя гипотеза", "kk": "әрқайсысының болжамы бар",
                       "en": "with a hypothesis each"},
    "kpi.frontier": {"ru": "оборванных ветвей", "kk": "үзілген тармақтар",
                     "en": "dead ends"},
    "kpi.frontier.sub": {"ru": "движение не прослежено — нужен запрос",
                         "kk": "қозғалыс тексерілмеген — сұраныс қажет",
                         "en": "flow not traced — request more"},

    "start.where": {"ru": "Куда смотреть", "kk": "Қайда қарау керек",
                    "en": "Where to go"},
    "start.card1": {
        "ru": "<b>1 · Кого проверять первым</b><br>Ранжированный список. Начните "
              "сверху и читайте колонку с обоснованием. Это и есть ответ на "
              "вопрос кейса.",
        "kk": "<b>1 · Алдымен кімді тексеру</b><br>Сұрыпталған тізім. Жоғарыдан "
              "бастап, негіздеме бағанын оқыңыз. Кейс сұрағының жауабы осы.",
        "en": "<b>1 · Who to review first</b><br>The ranked shortlist. Start at "
              "the top and read the reason column. This is the answer to the "
              "question the case asks."},
    "start.card2": {
        "ru": "<b>2 · Карточка счёта</b><br>Введите любой номер счёта: роль, "
              "<i>точное правило, которое её присвоило</i>, и карта движения "
              "денег вокруг него.",
        "kk": "<b>2 · Шот картасы</b><br>Кез келген шот нөмірін енгізіңіз: рөлі, "
              "<i>оны тағайындаған нақты ереже</i> және айналасындағы ақша "
              "қозғалысының картасы.",
        "en": "<b>2 · Account detail</b><br>Type any account number to get its "
              "role, <i>the exact rule that produced it</i>, and a map of the "
              "money moving through it."},
    "start.card3": {
        "ru": "<b>3 · Группы</b><br>Сеть, разбитая на сообщества, и гипотеза о "
              "назначении каждого.",
        "kk": "<b>3 · Топтар</b><br>Қауымдастықтарға бөлінген желі және "
              "әрқайсысының мақсаты туралы болжам.",
        "en": "<b>3 · Groups</b><br>The network split into communities, each "
              "with a hypothesis about what it is."},

    "start.classified": {"ru": "Как распределились роли",
                         "kk": "Рөлдер қалай бөлінді",
                         "en": "How the accounts were classified"},
    "start.rolekey": {"ru": "Что означает каждая роль",
                      "kk": "Әр рөлдің мағынасы",
                      "en": "What each role means"},
    "start.artifacts": {
        "ru": "<b>Почему так много «конечных получателей» и «обрывов»?</b> "
              "И то и другое — артефакты сбора данных, и оба обработаны "
              "осознанно. «Обрыв обхода» — счета на четвёртом колене, их "
              "исходящие переводы не запрашивались, поэтому мы говорим "
              "<i>неизвестно</i>, а не делаем вид, что деньги остановились. "
              "«Конечные получатели» прослежены, но большинство — обычные "
              "листья, у которых просто не было переводов выше порога "
              "в 5 000 ₸. Ни то, ни другое не считается сильным сигналом.",
        "kk": "<b>Неге «соңғы алушылар» мен «үзілістер» сонша көп?</b> Екеуі де "
              "— деректер жинау артефактілері және екеуі де саналы түрде "
              "өңделген. «Шолу шегі» — төртінші буындағы шоттар, олардың шығыс "
              "аударымдары сұралмаған, сондықтан біз ақша тоқтады деп "
              "көрсетпей, <i>белгісіз</i> дейміз. «Соңғы алушылар» тексерілген, "
              "бірақ көбі — 5 000 ₸ шегінен жоғары аударымы болмаған кәдімгі "
              "жапырақтар. Екеуі де күшті сигнал деп саналмайды.",
        "en": "<b>Why so many <i>terminal</i> and <i>cutoff</i>?</b> Both are "
              "artifacts of how the data was collected, and both are handled "
              "deliberately. <i>cutoff</i> accounts sit at the four-hop edge of "
              "the export — their onward transfers were never requested, so we "
              "say <i>unknown</i> rather than pretending the money stopped. "
              "<i>terminal</i> accounts were traced, but most are ordinary "
              "leaves that simply had nothing above the 5,000 KZT reporting "
              "floor leaving them. Neither is treated as a strong signal."},

    # ---- legend
    "legend.colors": {"ru": "Что означают цвета", "kk": "Түстердің мағынасы",
                      "en": "What the colours mean"},
    "legend.shapes": {"ru": "Формы и линии", "kk": "Пішіндер мен сызықтар",
                      "en": "Shapes and lines"},
    "legend.diamond": {
        "ru": "<b>◆ ромб</b> — один из 81 известного клиента",
        "kk": "<b>◆ ромб</b> — 81 белгілі клиенттің бірі",
        "en": "<b>◆ diamond</b> — one of the 81 known seed accounts"},
    "legend.circle": {
        "ru": "<b>● круг</b> — счёт, до которого дошёл обход",
        "kk": "<b>● шеңбер</b> — шолу жеткен шот",
        "en": "<b>● circle</b> — an account the trace reached"},
    "legend.dashed": {
        "ru": "<b>красный пунктир</b> — обход закончился здесь, дальше неизвестно",
        "kk": "<b>қызыл үзік сызық</b> — шолу осында аяқталды, әрі қарай белгісіз",
        "en": "<b>dashed red ring</b> — the export stopped here; onward flow unknown"},
    "legend.arrow": {
        "ru": "<b>стрелка</b> — направление движения денег",
        "kk": "<b>көрсеткі</b> — ақша қозғалысының бағыты",
        "en": "<b>arrow</b> — direction the money moved"},
    "legend.width": {
        "ru": "<b>толще линия</b> — больше сумма (лог. шкала)",
        "kk": "<b>қалың сызық</b> — сома үлкен (лог. шкала)",
        "en": "<b>thicker line</b> — larger amount (log scale)"},
    "legend.size": {
        "ru": "<b>крупнее круг</b> — выше приоритет проверки",
        "kk": "<b>үлкен шеңбер</b> — тексеру басымдығы жоғары",
        "en": "<b>bigger circle</b> — higher review priority"},
    "legend.key": {"ru": "Легенда: цвета и формы", "kk": "Аңыз: түстер мен пішіндер",
                   "en": "Colour and shape key"},

    "map.guide": {
        "ru": "<b>Как читать карту.</b> Деньги идут по стрелкам — от известных "
              "клиентов вверх, к тем, кто их собирает. Искомый счёт обведён "
              "чёрным. <b>Наведите на узел</b>, чтобы увидеть роль, суммы и "
              "краткое обоснование; <b>наведите на стрелку</b> — сумму и число "
              "переводов. Потяните, чтобы сдвинуть, колесо — масштаб.",
        "kk": "<b>Картаны қалай оқу керек.</b> Ақша көрсеткілер бойымен жүреді — "
              "белгілі клиенттерден жоғары, оларды жинайтындарға қарай. "
              "Ізделген шот қара түспен қоршалған. Рөлін, сомаларын және қысқа "
              "негіздемесін көру үшін <b>түйінге меңзеңіз</b>; соманы және "
              "аударым санын көру үшін <b>көрсеткіге меңзеңіз</b>. Жылжыту үшін "
              "сүйреңіз, масштаб үшін дөңгелекті бұраңыз.",
        "en": "<b>How to read this map.</b> Money flows along the arrows, away "
              "from the known seed accounts and up towards whoever collects it. "
              "The account you searched for is outlined in black. <b>Hover any "
              "node</b> for its role, amounts and the one-line evidence; "
              "<b>hover any arrow</b> for the amount and number of transfers. "
              "Drag to pan, scroll to zoom."},

    # ---- shortlist
    "prio.title": {"ru": "Список на проверку", "kk": "Тексеру тізімі",
                   "en": "The shortlist"},
    "prio.lead": {
        "ru": "Каждый счёт оценён по пяти признакам и отсортирован по убыванию. "
              "Последняя колонка простыми словами объясняет, почему он здесь.",
        "kk": "Әр шот бес белгі бойынша бағаланып, кему ретімен сұрыпталған. "
              "Соңғы баған неге осында екенін қарапайым тілмен түсіндіреді.",
        "en": "Every account scored on five signals, ranked highest first. The "
              "last column says, in plain language, what put it there."},
    "prio.note": {
        "ru": "<b>Нажмите на строку</b>, чтобы открыть карточку счёта ниже. "
              "Оценка складывается из: роли, объёма прослеженных денег от "
              "известных клиентов, числа независимых цепочек, числа разных "
              "плательщиков и насыщенности группы. <b>Известные 81 намеренно "
              "опущены вниз</b> — они уже у полиции, ценность в том, кто над ними.",
        "kk": "Шот картасын төменде ашу үшін <b>жолды басыңыз</b>. Бағалау "
              "мыналардан құралады: рөлі, белгілі клиенттерден келген ақша "
              "көлемі, тәуелсіз тізбектер саны, әртүрлі төлеушілер саны және "
              "топтың қанықтығы. <b>Белгілі 81 әдейі төмен түсірілген</b> — "
              "олар полицияда бар, құндылық олардың үстіндегілерде.",
        "en": "<b>Click any row</b> to open that account's full detail below. "
              "The score combines: its role, how much seed-linked money flows "
              "through it, how many separate courier chains reach it, how many "
              "different payers it has, and how seed-heavy its group is. "
              "<b>Known seeds are deliberately pushed down</b> — police already "
              "have those 81; the value is in what sits above them."},
    "col.rank": {"ru": "№", "kk": "№", "en": "#"},
    "col.account": {"ru": "Счёт", "kk": "Шот", "en": "Account"},
    "col.role": {"ru": "Роль", "kk": "Рөлі", "en": "Role"},
    "col.priority": {"ru": "Приоритет", "kk": "Басымдық", "en": "Priority"},
    "col.why": {"ru": "Почему он в списке", "kk": "Неге тізімде",
                "en": "Why it is on this list"},

    # ---- account
    "acc.title": {"ru": "Найти счёт", "kk": "Шотты табу", "en": "Look up an account"},
    "acc.lead": {
        "ru": "Введите номер счёта: роль, точное правило, которое её присвоило, "
              "и как через него движутся деньги.",
        "kk": "Шот нөмірін енгізіңіз: рөлі, оны тағайындаған нақты ереже және "
              "ақшаның ол арқылы қалай жүретіні.",
        "en": "Type any account number to see its role, the exact rule that "
              "produced it, and how money moves through it."},
    "acc.input": {"ru": "Номер счёта", "kk": "Шот нөмірі", "en": "Account number"},
    "acc.placeholder": {"ru": "вставьте gid и нажмите Enter",
                        "kk": "gid қойып, Enter басыңыз",
                        "en": "paste a gid, then press Enter"},
    "acc.pick": {"ru": "…или выберите из списка", "kk": "…немесе тізімнен таңдаңыз",
                 "en": "…or pick from the shortlist"},
    "acc.hops": {"ru": "Насколько широко рисовать", "kk": "Қаншалықты кең сызу",
                 "en": "How far around it to draw"},
    "acc.hops.info": {
        "ru": "1 — только прямые контрагенты (нагляднее). 2 — и их контрагенты.",
        "kk": "1 — тек тікелей контрагенттер (анығырақ). 2 — олардың "
              "контрагенттері де.",
        "en": "1 = direct counterparties only (clearest). 2 = their "
              "counterparties too."},
    "acc.amounts": {"ru": "Подписывать стрелки суммами",
                    "kk": "Көрсеткілерге сома жазу",
                    "en": "Label arrows with amounts"},
    "acc.amounts.info": {
        "ru": "Без подписей карта читается легче; сумма всегда есть во "
              "всплывающей подсказке.",
        "kk": "Жазусыз карта оңай оқылады; сома әрқашан қалқымалы кеңесте бар.",
        "en": "Off keeps the map readable; the amount is always in the tooltip."},
    "acc.mapheading": {"ru": "Движение денег вокруг счёта",
                       "kk": "Шот айналасындағы ақша қозғалысы",
                       "en": "The money around this account"},
    "acc.payers": {"ru": "Приход — кто платил этому счёту",
                   "kk": "Кіріс — бұл шотқа кім төледі",
                   "en": "Money in — who paid this account"},
    "acc.recipients": {"ru": "Расход — кому платил он",
                       "kk": "Шығыс — ол кімге төледі",
                       "en": "Money out — who it paid"},
    "acc.prompt": {"ru": "Введите номер счёта выше или выберите из списка.",
                   "kk": "Жоғарыда шот нөмірін енгізіңіз немесе тізімнен таңдаңыз.",
                   "en": "Type an account number above, or pick one from the list."},
    "acc.notfound": {"ru": "Счёт <b>{gid}</b> отсутствует в этих данных.",
                     "kk": "<b>{gid}</b> шоты бұл деректерде жоқ.",
                     "en": "Account <b>{gid}</b> is not in this dataset."},

    "f.priority": {"ru": "Приоритет проверки", "kk": "Тексеру басымдығы",
                   "en": "Review priority"},
    "f.confidence": {"ru": "Уверенность в роли", "kk": "Рөлге сенімділік",
                     "en": "Role confidence"},
    "f.received": {"ru": "Получено", "kk": "Алынды", "en": "Received"},
    "f.sent": {"ru": "Отправлено", "kk": "Жіберілді", "en": "Sent"},
    "f.reach": {"ru": "Сколько известных клиентов дотягиваются",
                "kk": "Қанша белгілі клиент жетеді",
                "en": "Seeds that can reach it"},
    "f.attributed": {"ru": "Оценка прослеженных денег",
                     "kk": "Тексерілген ақша бағасы",
                     "en": "Est. seed-linked flow"},
    "f.depth": {"ru": "Колен от известного клиента", "kk": "Белгілі клиенттен буын",
                "en": "Hops from a seed"},
    "f.isseed": {"ru": "Известный клиент", "kk": "Белгілі клиент",
                 "en": "Known seed account"},
    "f.cluster": {"ru": "Группа", "kk": "Тобы", "en": "Cluster"},
    "f.payers_n": {"ru": "от {n} плательщик(ов)", "kk": "{n} төлеушіден",
                   "en": "from {n} payer(s)"},
    "f.recipients_n": {"ru": "на {n} получател(я/ей)", "kk": "{n} алушыға",
                       "en": "to {n} recipient(s)"},
    "yes": {"ru": "да", "kk": "иә", "en": "yes"},
    "no": {"ru": "нет", "kk": "жоқ", "en": "no"},

    "acc.evidence": {"ru": "Обоснование", "kk": "Негіздеме", "en": "Evidence"},
    "acc.frontier_warn": {
        "ru": "<b>Осторожно.</b> Этот счёт стоит на краю выгрузки. Его "
              "исходящие переводы не запрашивались, поэтому <b>неизвестно</b>, "
              "остановились ли здесь деньги. Хороший кандидат на дополнительный "
              "запрос данных.",
        "kk": "<b>Абайлаңыз.</b> Бұл шот шолу шегінде тұр. Оның шығыс "
              "аударымдары сұралмаған, сондықтан ақша осында тоқтады ма — "
              "<b>белгісіз</b>. Қосымша деректер сұратуға лайықты үміткер.",
        "en": "<b>Careful.</b> This account sits at the edge of the export. Its "
              "outgoing transfers were never requested, so <b>we do not know</b> "
              "whether the money stopped here. It is a strong candidate for a "
              "follow-up data request."},
    "acc.also": {"ru": "Также подошло под", "kk": "Сондай-ақ сәйкес келді",
                 "en": "Also matched"},
    "acc.caveat": {"ru": "Замечание рецензента", "kk": "Рецензент ескертуі",
                   "en": "Reviewer's caveat"},

    "why.heading": {"ru": "Почему присвоена эта роль", "kk": "Неге осы рөл берілді",
                    "en": "Why it was classified this way"},
    "why.lead": {
        "ru": "*Это правило, которое применил движок. Модель ИИ не участвовала в "
              "присвоении роли — ниже те самые числа, которые сравнивало правило.*",
        "kk": "*Бұл — қозғалтқыш қолданған ереже. Рөлді тағайындауға ЖИ моделі "
              "қатыспаған — төменде ереже салыстырған нақты сандар.*",
        "en": "*This is the rule the engine applied. No AI model was involved in "
              "assigning the role — the numbers below are the ones the rule "
              "actually compared.*"},
    "why.rule": {"ru": "**Сработавшее правило**", "kk": "**Іске қосылған ереже**",
                 "en": "**Rule that fired**"},
    "why.values": {"ru": "**Использованные значения**",
                   "kk": "**Қолданылған мәндер**", "en": "**Values it used**"},
    "why.thresholds": {
        "ru": "**Пороги, с которыми сравнивалось** *(из `config.yaml`)*",
        "kk": "**Салыстырылған шектер** *(`config.yaml` файлынан)*",
        "en": "**Thresholds it compared against** *(from `config.yaml`)*"},
    "why.penalties": {"ru": "**Уверенность снижена, потому что**",
                      "kk": "**Сенімділік төмендеді, себебі**",
                      "en": "**Confidence reduced because**"},
    "why.adjust": {"ru": "**Поправка к приоритету.**",
                   "kk": "**Басымдық түзетуі.**",
                   "en": "**Priority adjustment.**"},
    "dossier.heading": {"ru": "Досье следователя-агента",
                        "kk": "Тергеуші-агент досьесі",
                        "en": "Investigator's dossier"},
    "dossier.pattern": {"ru": "**Паттерн.**", "kk": "**Үлгі.**", "en": "**Pattern.**"},
    "dossier.alt": {"ru": "**Может объясняться и так.**",
                    "kk": "**Былай да түсіндірілуі мүмкін.**",
                    "en": "**Could equally be.**"},
    "dossier.next": {"ru": "**Следующий шаг.**", "kk": "**Келесі қадам.**",
                     "en": "**Suggested next step.**"},
    "dossier.advisory": {
        "ru": "*Только рекомендация — на роль и место в списке это не повлияло.*",
        "kk": "*Тек ұсыныс — рөлге және тізімдегі орынға әсер етпеген.*",
        "en": "*Advisory only — this did not affect the role or the ranking.*"},

    # ---- groups
    "grp.title": {"ru": "Сообщества в сети", "kk": "Желідегі қауымдастықтар",
                  "en": "Communities in the network"},
    "grp.lead": {
        "ru": "Сеть разбита на группы счетов, которые двигают деньги между "
              "собой. Для каждой — гипотеза о назначении.",
        "kk": "Желі өзара ақша жүргізетін шоттар топтарына бөлінген. "
              "Әрқайсысы үшін — мақсаты туралы болжам.",
        "en": "The network split into groups of accounts that move money among "
              "themselves. Each one gets a hypothesis about what it looks like."},
    "grp.note": {
        "ru": "Группировка — метод Лувена на <b>неориентированной</b> проекции: "
              "выделение сообществ требует именно её. Направление отброшено "
              "<i>только для группировки</i>: все роли, числа и стрелки в "
              "остальном интерфейсе используют реальное направление денег. "
              "Мелкие несвязные фрагменты остаются отдельными группами, а не "
              "растворяются в большой.",
        "kk": "Топтастыру — <b>бағытсыз</b> проекциядағы Лувен әдісі: "
              "қауымдастықтарды бөлу дәл соны талап етеді. Бағыт <i>тек "
              "топтастыру үшін</i> алынып тасталды: қалған интерфейстегі "
              "барлық рөлдер, сандар мен көрсеткілер ақшаның нақты бағытын "
              "пайдаланады. Ұсақ байланыссыз фрагменттер үлкеніне қосылмай, "
              "жеке топ болып қалады.",
        "en": "Grouping uses the Louvain method on an <b>undirected</b> view of "
              "the network — community detection needs one. Direction is "
              "dropped <i>for grouping only</i>: every role, number and arrow "
              "elsewhere still uses the real direction of the money. Small "
              "disconnected fragments are kept as their own groups rather than "
              "being folded into the big one."},
    "grp.show": {"ru": "Показать группу", "kk": "Топты көрсету", "en": "Show group"},
    "grp.members": {"ru": "Счета в этой группе", "kk": "Осы топтағы шоттар",
                    "en": "Accounts in this group"},
    "grp.hypothesis": {"ru": "Гипотеза", "kk": "Болжам", "en": "Hypothesis"},
    "grp.word": {"ru": "Группа", "kk": "Топ", "en": "Group"},
    "grp.accounts": {"ru": "счетов", "kk": "шот", "en": "accounts"},
    "grp.seeds": {"ru": "известных клиентов", "kk": "белгілі клиент",
                  "en": "known seeds"},
    "grp.internal": {"ru": "движется внутри группы",
                     "kk": "топ ішінде жүреді",
                     "en": "moving inside the group"},
    "col.groupid": {"ru": "Группа", "kk": "Топ", "en": "Group"},
    "col.naccounts": {"ru": "Счетов", "kk": "Шоттар", "en": "Accounts"},
    "col.nseeds": {"ru": "Известных", "kk": "Белгілі", "en": "Known seeds"},
    "col.internal": {"ru": "Оборот внутри", "kk": "Ішкі айналым",
                     "en": "Internal flow"},
    "col.looks": {"ru": "На что похоже", "kk": "Неге ұқсайды",
                  "en": "What it looks like"},
    "col.evidence": {"ru": "Обоснование", "kk": "Негіздеме", "en": "Evidence"},
    "col.itsrole": {"ru": "Его роль", "kk": "Оның рөлі", "en": "Its role"},
    "col.seedq": {"ru": "Известный?", "kk": "Белгілі ме?", "en": "Seed?"},
    "col.amount": {"ru": "Сумма (₸)", "kk": "Сома (₸)", "en": "Amount (KZT)"},
    "col.transfers": {"ru": "Переводов", "kk": "Аударымдар", "en": "Transfers"},

    # ---- ask
    "ask.title": {"ru": "Спросить о сети", "kk": "Желі туралы сұрау",
                  "en": "Ask about the network"},
    "ask.lead": {
        "ru": "Вопросы обычным языком. Ответ собирается только из "
              "детерминированных запросов к графу — раскройте блок под ответом, "
              "чтобы увидеть, из каких именно.",
        "kk": "Қарапайым тілдегі сұрақтар. Жауап тек графқа жасалған "
              "детерминделген сұраулардан құралады — қайсысынан екенін көру "
              "үшін жауап астындағы блокты ашыңыз.",
        "en": "Questions in plain English. The answer is assembled only from "
              "deterministic queries against the graph — expand the disclosure "
              "under any answer to see exactly which ones."},
    "ask.note": {
        "ru": "Без подключённой модели это тоже работает: те же запросы "
              "выполняются, просто формулировки проще. Выдумать номер счёта "
              "здесь невозможно — несуществующий отбрасывается.",
        "kk": "Модель қосылмаса да жұмыс істейді: сол сұраулар орындалады, тек "
              "тұжырымдамасы қарапайым. Шот нөмірін ойдан шығару мүмкін емес — "
              "жоқ нөмір алынып тасталады.",
        "en": "Without a model configured this still works: the same queries "
              "run, the phrasing is just plainer. Nothing here can invent an "
              "account number — one that does not exist is dropped."},
    "ask.q": {"ru": "Ваш вопрос", "kk": "Сіздің сұрағыңыз", "en": "Your question"},
    "ask.placeholder": {
        "ru": "например: кто собирает деньги с этих пяти? 1234; 5678; …",
        "kk": "мысалы: осы бесеуден ақшаны кім жинайды? 1234; 5678; …",
        "en": "e.g. who collects money from these five? 1234; 5678; …"},
    "ask.send": {"ru": "Спросить", "kk": "Сұрау", "en": "Ask"},
    "ask.clear": {"ru": "Очистить", "kk": "Тазалау", "en": "Clear"},
    "ask.examples": {"ru": "Попробуйте один из этих", "kk": "Мыналардың бірін көріңіз",
                     "en": "Try one of these"},
    "ask.ex1": {"ru": "Какие счета проверять первыми и почему?",
                "kk": "Қай шоттарды алдымен тексеру керек және неге?",
                "en": "Which accounts should I review first, and why?"},
    "ask.ex2": {"ru": "Какие точки сбора стоят на краю выгрузки?",
                "kk": "Қай жинау нүктелері шолу шегінде тұр?",
                "en": "Which collection points sit at the edge of the export?"},
    "ask.ex3": {"ru": "Что нужно запросить, чтобы увидеть дальше четвёртого колена?",
                "kk": "Төртінші буыннан әрі көру үшін нені сұрату керек?",
                "en": "What would I need to request to see past the fourth hop?"},
    "ask.queries": {"ru": "Запросы к графу, на которых построен ответ: {n}",
                    "kk": "Жауап негізделген графқа сұраулар: {n}",
                    "en": "The {n} graph queries this answer is built from"},

    # ---- agents
    "ag.title": {"ru": "Команда агентов и её полномочия",
                 "kk": "Агенттер тобы және оның өкілеттігі",
                 "en": "The agent crew, and what it was allowed to do"},
    "ag.lead": {
        "ru": "ИИ-агенты решали, <b>что изучать и какими должны быть пороги</b>. "
              "Детерминированный движок правил присвоил <b>каждую роль, оценку, "
              "группу и место в списке</b>. Ни один агент не может изменить "
              "классификацию.",
        "kk": "ЖИ-агенттер <b>нені зерттеу керектігін және шектер қандай болуы "
              "тиіс екенін</b> шешті. Детерминделген ережелер қозғалтқышы "
              "<b>әр рөлді, бағаны, топты және тізімдегі орынды</b> "
              "тағайындады. Ешбір агент жіктемені өзгерте алмайды.",
        "en": "AI agents chose <b>what to examine and what the thresholds should "
              "be</b>. A deterministic rule engine decided <b>every role, score, "
              "cluster and rank</b>. No agent can change a classification."},
    "ag.thresholds": {"ru": "Пороги, выбранные агентом-калибровщиком",
                      "kk": "Калибрлеуші агент таңдаған шектер",
                      "en": "Thresholds the calibrator agent chose"},
    "ag.thresholds.note": {
        "ru": "Агент изучил реальное распределение каждой метрики и выбрал эти "
              "числа, написав обоснование к каждому. Перед принятием каждый "
              "набор <b>моделировался на фактических данных</b>: набор, "
              "обнуляющий роль или отдающий одной роли половину сети, "
              "отклоняется, и остаются заданные вручную значения. Результат "
              "сохраняется и переиспользуется, поэтому запуск воспроизводим.",
        "kk": "Агент әр метриканың нақты таралуын зерттеп, осы сандарды таңдады "
              "және әрқайсысына негіздеме жазды. Қабылданғанға дейін әр жиын "
              "<b>нақты деректерде модельденді</b>: рөлді нөлдейтін немесе бір "
              "рөлге желінің жартысын беретін жиын қабылданбайды, қолмен "
              "қойылған мәндер қалады. Нәтиже сақталып, қайта қолданылады, "
              "сондықтан іске қосу қайталанады.",
        "en": "The agent read the real distribution of every metric and picked "
              "these numbers, writing a justification for each. Before being "
              "accepted, each set was <b>simulated against the actual data</b> — "
              "a set that emptied a role, or handed one role half the network, "
              "is rejected and the hand-set defaults stand. The result is saved "
              "and reused, so the run reproduces exactly."},
    "ag.dossiers": {"ru": "Досье по счетам", "kk": "Шоттар бойынша досье",
                    "en": "Case dossiers"},
    "ag.dossiers.note": {
        "ru": "По каждому счёту из верха списка агент провёл многошаговое "
              "расследование, используя только запросы к графу. Он обязан "
              "предложить правдоподобное <b>безобидное</b> объяснение — "
              "зарплатный счёт и точка сбора в этих данных выглядят одинаково.",
        "kk": "Тізім басындағы әр шот бойынша агент тек графқа сұраулар "
              "қолданып, көп қадамды тергеу жүргізді. Ол сенімді "
              "<b>зиянсыз</b> түсіндірме ұсынуға міндетті — жалақы шоты мен "
              "жинау нүктесі бұл деректерде бірдей көрінеді.",
        "en": "For each top account, an agent ran a multi-step investigation "
              "using only graph queries. It is required to offer a plausible "
              "<b>innocent</b> explanation — a payroll account and a collection "
              "point look identical in this data."},
    "ag.critic": {"ru": "Аргументы против этого списка",
                  "kk": "Осы тізімге қарсы дәлелдер",
                  "en": "The argument against this shortlist"},
    "ag.critic.note": {
        "ru": "Агента-рецензента попросили атаковать результат: какие позиции "
              "высоко из-за способа сбора данных, какие пороги делают "
              "подозрительно много работы, чего не хватает. Проверять не с чем, "
              "поэтому это ближайшее к контролю, что вообще существует.",
        "kk": "Рецензент-агенттен нәтижеге шабуыл жасау сұралды: қай позициялар "
              "деректер жинау тәсілінен жоғары, қай шектер күмәнді көп жұмыс "
              "істейді, не жетіспейді. Салыстыратын эталон жоқ, сондықтан бұл "
              "— бақылауға ең жақын нәрсе.",
        "en": "A reviewer agent was asked to attack the results: which entries "
              "rank highly because of how the data was collected, which "
              "thresholds are doing suspicious work, what is missing. With no "
              "ground truth to validate against, this is the closest thing to a "
              "check that exists."},
    "ag.log": {"ru": "Полный журнал агентов — каждое действие и вызов функции",
               "kk": "Агенттердің толық журналы — әр әрекет пен функция шақыруы",
               "en": "Full audit log — every agent action and tool call"},
    "ag.requests": {"ru": "Каких данных не хватает и что запросить дальше",
                    "kk": "Қандай деректер жетіспейді және не сұрату керек",
                    "en": "What data is missing, and what to request next"},
    "col.threshold": {"ru": "Порог", "kk": "Шек", "en": "Threshold"},
    "col.value": {"ru": "Значение", "kk": "Мәні", "en": "Value"},
    "col.whychosen": {"ru": "Почему агент выбрал это число",
                      "kk": "Агент неге осы санды таңдады",
                      "en": "Why the agent chose this number"},
    "col.pattern": {"ru": "Паттерн", "kk": "Үлгі", "en": "Pattern"},
    "col.found": {"ru": "Что обнаружил агент", "kk": "Агент нені анықтады",
                  "en": "What the investigator found"},
    "col.alt": {"ru": "Может быть и этим", "kk": "Мынау да болуы мүмкін",
                "en": "Could equally be"},
    "col.next": {"ru": "Следующий шаг", "kk": "Келесі қадам", "en": "Next step"},

    # ---- data
    "data.title": {"ru": "Что было загружено", "kk": "Не жүктелді",
                   "en": "What was loaded"},
    "data.lead": {
        "ru": "Инструменту не обязательны три файла из условия кейса. Он читает "
              "любую табличную выгрузку и сам определяет, какая колонка за что "
              "отвечает.",
        "kk": "Құралға кейс шартындағы үш файл міндетті емес. Ол кез келген "
              "кестелік деректерді оқып, қай баған не үшін жауап беретінін "
              "өзі анықтайды.",
        "en": "This tool does not require the three files from the case pack. It "
              "reads whatever tabular export you point it at and works out which "
              "column is which."},
    "data.files": {"ru": "Файлы, использованные в этом запуске",
                   "kk": "Осы іске қосуда пайдаланылған файлдар",
                   "en": "Files used in this run"},
    "data.mapping": {"ru": "Как распознана каждая колонка",
                     "kk": "Әр баған қалай танылды",
                     "en": "How each column was understood"},
    "data.mapping.note": {
        "ru": "Колонки сопоставляются сначала по имени (список синонимов "
              "покрывает <code>from</code>/<code>payer</code>/<code>src</code>, "
              "<code>amount</code>/<code>sum_kzt</code>/<code>value</code> и "
              "так далее), затем по структуре: колонка с датой — это дата, пара "
              "целочисленных колонок с пересекающимися значениями — два конца "
              "перевода. Нераспознанное передаётся агенту, чей ответ "
              "<b>перепроверяется по самим данным</b> перед принятием.",
        "kk": "Бағандар алдымен атауы бойынша сәйкестендіріледі (синонимдер "
              "тізімі <code>from</code>/<code>payer</code>/<code>src</code>, "
              "<code>amount</code>/<code>sum_kzt</code>/<code>value</code> және "
              "т.б. қамтиды), содан кейін құрылымы бойынша: күні бар баған — "
              "күн, мәндері қиылысатын бүтін сандық бағандар жұбы — аударымның "
              "екі ұшы. Танылмағаны агентке беріледі, оның жауабы қабылданғанға "
              "дейін <b>деректердің өзімен тексеріледі</b>.",
        "en": "Columns are matched by name first (an alias list covers "
              "<code>from</code>/<code>payer</code>/<code>src</code>, "
              "<code>amount</code>/<code>sum_kzt</code>/<code>value</code>, and "
              "so on), then by structure — a date column is the date, the "
              "integer pair whose values overlap is the two ends of a transfer. "
              "Anything still unresolved is passed to an agent, whose answer is "
              "<b>re-checked against the data</b> before it is accepted."},
    "data.own": {
        "ru": "<b>Чтобы запустить на своей выгрузке:</b> положите файлы в папку "
              "и выполните <code>./agent_run.sh --data /путь/к/папке</code>. "
              "Читаются parquet, CSV, TSV, JSON, JSONL и XLSX. Если списка "
              "счетов нет — он выводится из переводов; если нет номера колена — "
              "он пересчитывается; если нет отметки известного клиента — ими "
              "считаются счета без входящих, и отчёт прямо об этом говорит, "
              "потому что это предположение определяет все роли.",
        "kk": "<b>Өз деректеріңізде іске қосу үшін:</b> файлдарды бір қалтаға "
              "салып, <code>./agent_run.sh --data /жол/қалтаға</code> "
              "орындаңыз. parquet, CSV, TSV, JSON, JSONL және XLSX оқылады. "
              "Шоттар тізімі болмаса — аударымдардан шығарылады; буын нөмірі "
              "болмаса — қайта есептеледі; белгілі клиент белгісі болмаса — "
              "кірісі жоқ шоттар солай саналады, және есеп мұны анық айтады, "
              "өйткені бұл жорамал барлық рөлді анықтайды.",
        "en": "<b>To run this on your own export:</b> put the files in a folder "
              "and run <code>./agent_run.sh --data /path/to/folder</code>. "
              "Parquet, CSV, TSV, JSON, JSONL and XLSX are all read. If there is "
              "no account list, it is derived from the transfers; if there is no "
              "hop number, it is recomputed; if there is no seed flag, accounts "
              "with no traced inflow are treated as seeds — and the report says "
              "so, because that assumption drives every role."},
    "data.derived": {"ru": "<b>Выведено, а не получено из файла.</b>",
                     "kk": "<b>Файлдан алынбай, есептелген.</b>",
                     "en": "<b>Derived, not supplied.</b>"},
    "data.allsupplied": {
        "ru": "Всё необходимое присутствовало во входных данных. Ничего "
              "выводить не пришлось.",
        "kk": "Қажеттінің бәрі кіріс деректерде болды. Ештеңе есептеудің "
              "қажеті болмады.",
        "en": "Everything the pipeline needed was present in the input. Nothing "
              "had to be inferred."},
    "data.profile": {"ru": "Полный профиль данных — все заявленные факты проверены",
                     "kk": "Толық дерек профилі — мәлімделген фактілер тексерілді",
                     "en": "Full data profile — every announced fact checked"},
    "col.file": {"ru": "Файл", "kk": "Файл", "en": "File"},
    "col.readas": {"ru": "Прочитан как", "kk": "Қалай оқылды", "en": "Read as"},
    "col.stdfield": {"ru": "Стандартное поле", "kk": "Стандартты өріс",
                     "en": "Standard field"},
    "col.yourcol": {"ru": "Колонка в вашем файле", "kk": "Сіздің файлдағы баған",
                    "en": "Column in your file"},
    "col.matchedby": {"ru": "Распознано", "kk": "Қалай танылды", "en": "Matched by"},

    # ---- cost
    "cost.title": {"ru": "Во что обошёлся запуск", "kk": "Іске қосу неге түсті",
                   "en": "What this run cost"},
    "cost.lead": {"ru": "Каждый этап замерен, каждый токен посчитан, каждый "
                        "вызов оценён.",
                  "kk": "Әр кезең өлшенді, әр токен саналды, әр шақыру бағаланды.",
                  "en": "Every stage timed, every token counted, every call priced."},
    "cost.note": {
        "ru": "Число токенов — ровно то, что сообщил провайдер, без оценок на "
              "глаз. Если у модели не заданы тарифы, стоимость показывается как "
              "<b>не тарифицировано</b>, а не числом, которое выглядит "
              "авторитетно.",
        "kk": "Токен саны — провайдер хабарлаған дәл сан, болжам емес. Модельдің "
              "тарифі берілмесе, құны сенімді көрінетін санмен емес, "
              "<b>тарифсіз</b> деп көрсетіледі.",
        "en": "Token counts are exactly what the provider reported — never "
              "estimated. If a model has no rates configured, the spend reads "
              "<b>unpriced</b> rather than showing a number that looks "
              "authoritative."},
    "cost.runtime": {"ru": "общее время", "kk": "жалпы уақыт", "en": "total runtime"},
    "cost.budget": {"ru": "лимит {n}с", "kk": "шек {n}с", "en": "budget {n}s"},
    "cost.calls": {"ru": "вызовов модели", "kk": "модель шақырулары",
                   "en": "model calls"},
    "cost.failed": {"ru": "{n} с ошибкой", "kk": "{n} қатемен", "en": "{n} failed"},
    "cost.allok": {"ru": "все успешно", "kk": "барлығы сәтті", "en": "all succeeded"},
    "cost.tokens": {"ru": "токенов", "kk": "токен", "en": "tokens"},
    "cost.reasoning": {"ru": "{n} на рассуждение", "kk": "{n} пайымдауға",
                       "en": "{n} reasoning"},
    "cost.spend": {"ru": "стоимость", "kk": "құны", "en": "spend"},
    "cost.thisrun": {"ru": "этот запуск", "kk": "осы іске қосу", "en": "this run"},
    "cost.unpriced": {"ru": "не тарифицировано", "kk": "тарифсіз", "en": "unpriced"},

    # ---- downloads
    "dl.title": {"ru": "Результаты", "kk": "Нәтижелер", "en": "Deliverables"},
    "dl.lead": {"ru": "Три обязательные выгрузки и всё, что читает интерфейс.",
                "kk": "Үш міндетті файл және интерфейс оқитын барлық нәрсе.",
                "en": "The three required exports, plus everything the viewer reads."},
    "dl.button": {"ru": "Скачать", "kk": "Жүктеп алу", "en": "Download"},
    "dl.note": {
        "ru": "<b>nodes_roles.csv</b> — строка на счёт: роль, уверенность, "
              "группа, приоритет и обоснование.<br><b>clusters.csv</b> — строка "
              "на группу с гипотезой.<br><b>top_nodes.csv</b> — список на "
              "проверку с обоснованиями.<br><br><i>Выгрузки формируются на "
              "английском: их схему жюри проверяет механически.</i>",
        "kk": "<b>nodes_roles.csv</b> — әр шотқа жол: рөлі, сенімділігі, тобы, "
              "басымдығы және негіздемесі.<br><b>clusters.csv</b> — әр топқа "
              "жол, болжамымен.<br><b>top_nodes.csv</b> — негіздемесі бар "
              "тексеру тізімі.<br><br><i>Файлдар ағылшын тілінде жасалады: "
              "олардың схемасын қазылар алқасы механикалық тексереді.</i>",
        "en": "<b>nodes_roles.csv</b> — one row per account: role, confidence, "
              "group, priority and the evidence sentence.<br>"
              "<b>clusters.csv</b> — one row per group, with its hypothesis.<br>"
              "<b>top_nodes.csv</b> — the ranked shortlist with reasons."},
    "dl.preview": {"ru": "nodes_roles.csv — первые 40 строк",
                   "kk": "nodes_roles.csv — алғашқы 40 жол",
                   "en": "nodes_roles.csv — first 40 rows"},

    # ---- misc
    "lang.label": {"ru": "Язык", "kk": "Тіл", "en": "Language"},
    "nomaps": {"ru": "Результатов пока нет", "kk": "Әзірге нәтиже жоқ",
               "en": "No results yet"},
    "notgenerated": {"ru": "*не сформировано*", "kk": "*жасалмаған*",
                     "en": "*not generated*"},
    "map.capped": {
        "ru": "В этой окрестности больше {cap} счетов, поэтому нарисованы "
              "только {cap} самых крупных потоков. Переключитесь на 1 колено, "
              "чтобы увидеть картину целиком.",
        "kk": "Бұл маңайда {cap} шоттан көп, сондықтан тек {cap} ең ірі ағын "
              "сызылған. Толық көрініс үшін 1 буынға ауысыңыз.",
        "en": "This neighbourhood has more than {cap} accounts, so only the "
              "{cap} largest flows are drawn. Switch to 1 hop for the full "
              "picture."},
    "map.capped_cluster": {
        "ru": "Показаны {cap} счетов с наибольшим приоритетом из {total} в группе.",
        "kk": "Топтағы {total} шоттың басымдығы ең жоғары {cap} көрсетілген.",
        "en": "Showing the {cap} highest-priority of {total} accounts in this group."},
}

# ---------------------------------------------------------------------------
# introduction tab + per-tab purpose lines
# ---------------------------------------------------------------------------

_INTRO = {
    "tab.about": {"ru": "О решении", "kk": "Шешім туралы", "en": "About"},

    "about.title": {"ru": "Граф денег — как этим пользоваться",
                    "kk": "Ақша графы — оны қалай пайдалану",
                    "en": "Money Graph — how to use this"},
    "about.lead": {
        "ru": "Инструмент восстанавливает финансовую структуру организованной "
              "группы по сети переводов. На входе — выгрузка исходящих "
              "переводов от известных клиентов; на выходе — ранжированный "
              "список счетов с ролью, обоснованием и картой связей.<br><br>"
              "Эта вкладка объясняет, что находится на остальных восьми и в "
              "каком порядке их смотреть.",
        "kk": "Құрал аударымдар желісі бойынша ұйымдасқан топтың қаржылық "
              "құрылымын қалпына келтіреді. Кірісте — белгілі клиенттердің "
              "шығыс аударымдары; шығыста — рөлі, негіздемесі және "
              "байланыстар картасы бар шоттардың сұрыпталған тізімі.<br><br>"
              "Бұл қойынды қалған сегізінде не бар екенін және оларды қандай "
              "ретпен қарау керектігін түсіндіреді.",
        "en": "The tool reconstructs the financial structure of an organized "
              "group from a transfer network. In: an export of outgoing "
              "transfers from known customers. Out: a ranked list of accounts, "
              "each with a role, a written reason and a map of its links."
              "<br><br>This tab explains what is on the other eight and in "
              "what order to look at them."},

    "about.steps": {"ru": "Как пройти основной сценарий за три шага",
                    "kk": "Негізгі сценарийді үш қадамда өту",
                    "en": "The main scenario in three steps"},
    "about.step1": {
        "ru": "<b>Шаг 1 — «Кого проверять первым».</b> Открыть вкладку и "
              "прочитать верхние строки. Колонка «Почему он в списке» "
              "объясняет каждую позицию обычными словами. Это и есть ответ "
              "на вопрос кейса.",
        "kk": "<b>1-қадам — «Алдымен кімді тексеру».</b> Қойындыны ашып, "
              "жоғарғы жолдарды оқыңыз. «Неге тізімде» бағаны әр позицияны "
              "қарапайым сөзбен түсіндіреді. Кейс сұрағының жауабы осы.",
        "en": "<b>Step 1 — Who to review first.</b> Open the tab and read the "
              "top rows. The <i>Why it is on this list</i> column explains "
              "each entry in plain words. This is the answer to the case "
              "question."},
    "about.step2": {
        "ru": "<b>Шаг 2 — «Карточка счёта».</b> Ввести любой номер счёта. "
              "Показываются роль, <i>точное правило, которое её присвоило</i>, "
              "все использованные числа и карта движения денег вокруг счёта. "
              "Именно так проверяется требование «объяснить любой gid за "
              "минуту».",
        "kk": "<b>2-қадам — «Шот картасы».</b> Кез келген шот нөмірін "
              "енгізіңіз. Рөлі, <i>оны тағайындаған нақты ереже</i>, "
              "қолданылған барлық сандар және шот айналасындағы ақша "
              "қозғалысының картасы көрсетіледі. «Кез келген gid-ті бір "
              "минутта түсіндіру» талабы дәл осылай тексеріледі.",
        "en": "<b>Step 2 — Account detail.</b> Type any account number. You get "
              "the role, <i>the exact rule that produced it</i>, every number "
              "the rule used, and a map of the money around it. This is how "
              "the \u201cexplain any gid in a minute\u201d requirement is met."},
    "about.step3": {
        "ru": "<b>Шаг 3 — «Как принято решение».</b> Проверить, что система не "
              "«чёрный ящик»: пороги, выбранные агентом, с обоснованием "
              "каждого; досье по счетам; аргументы <i>против</i> собственного "
              "результата; полный журнал действий агентов.",
        "kk": "<b>3-қадам — «Шешім қалай қабылданды».</b> Жүйенің «қара жәшік» "
              "емес екенін тексеріңіз: агент таңдаған шектер әрқайсысының "
              "негіздемесімен; шоттар бойынша досье; өз нәтижесіне "
              "<i>қарсы</i> дәлелдер; агенттер әрекеттерінің толық журналы.",
        "en": "<b>Step 3 — How it decided.</b> Confirm the system is not a "
              "black box: the thresholds an agent chose with a justification "
              "for each, the case dossiers, the argument <i>against</i> its own "
              "result, and the full agent action log."},

    "about.map": {"ru": "Что на каждой вкладке", "kk": "Әр қойындыда не бар",
                  "en": "What is on each tab"},
    "about.col.tab": {"ru": "Вкладка", "kk": "Қойынды", "en": "Tab"},
    "about.col.for": {"ru": "Для чего", "kk": "Не үшін", "en": "What it is for"},
    "about.col.when": {"ru": "Когда смотреть", "kk": "Қашан қарау керек",
                       "en": "When to use it"},

    "about.safety": {
        "ru": "<b>Как читать любые выводы.</b> Всё в интерфейсе — гипотезы для "
              "проверки аналитиком, а не утверждения о факте. Роли присваивает "
              "детерминированный движок правил: у каждой роли есть формальное "
              "правило с порогом, и это правило показано в карточке счёта. "
              "ИИ-агенты решают, <i>что изучать и какими должны быть пороги</i>, "
              "но не могут изменить ни роль, ни оценку, ни место в списке.",
        "kk": "<b>Кез келген қорытындыны қалай оқу керек.</b> Интерфейстегінің "
              "бәрі — талдаушы тексеретін болжамдар, дәлелденген факт емес. "
              "Рөлдерді детерминделген ережелер қозғалтқышы тағайындайды: әр "
              "рөлдің шегі бар формалды ережесі бар және ол ереже шот "
              "картасында көрсетілген. ЖИ-агенттер <i>нені зерттеу керектігін "
              "және шектер қандай болуы тиіс екенін</i> шешеді, бірақ рөлді де, "
              "бағаны да, тізімдегі орынды да өзгерте алмайды.",
        "en": "<b>How to read anything here.</b> Everything in this interface is "
              "a hypothesis for an analyst to verify, not a finding of fact. "
              "Roles are assigned by a deterministic rule engine: every role "
              "has a formal rule with a threshold, and that rule is shown on "
              "the account card. AI agents decide <i>what to examine and what "
              "the thresholds should be</i>, but cannot change a role, a score "
              "or a rank."},

    # --- per-tab purpose lines, shown at the top of each tab ---------------
    "purpose.priority": {
        "ru": "<b>Назначение вкладки.</b> Ответить на главный вопрос кейса: "
              "кого из 2 248 клиентов проверять первым и почему. Список "
              "отсортирован по убыванию приоритета; нажатие на строку "
              "открывает карточку счёта ниже.",
        "kk": "<b>Қойындының мақсаты.</b> Кейстің негізгі сұрағына жауап беру: "
              "2 248 клиенттің қайсысын алдымен тексеру керек және неге. Тізім "
              "басымдығы бойынша кему ретімен сұрыпталған; жолды басқанда "
              "төменде шот картасы ашылады.",
        "en": "<b>What this tab is for.</b> Answering the case's main question: "
              "which of the 2,248 customers to review first, and why. Sorted by "
              "descending priority; clicking a row opens that account's card "
              "below."},
    "purpose.account": {
        "ru": "<b>Назначение вкладки.</b> Объяснить один конкретный счёт. Роль, "
              "сработавшее правило с числами, связи и карта потоков. Это "
              "рабочее место аналитика и путь демонстрации: жюри называет gid — "
              "ответ виден здесь за секунды.",
        "kk": "<b>Қойындының мақсаты.</b> Бір нақты шотты түсіндіру. Рөлі, "
              "сандарымен қоса іске қосылған ереже, байланыстары және ағындар "
              "картасы. Бұл — талдаушының жұмыс орны және демонстрация жолы: "
              "қазылар gid атайды — жауап осында бірнеше секундта көрінеді.",
        "en": "<b>What this tab is for.</b> Explaining one specific account: its "
              "role, the rule that fired with its numbers, its counterparties "
              "and a flow map. This is the analyst's workbench and the demo "
              "path: the jury names a gid, the answer is here in seconds."},
    "purpose.groups": {
        "ru": "<b>Назначение вкладки.</b> Показать, что сеть не монолитна. "
              "Счета разбиты на сообщества; у каждого — размер, число "
              "известных клиентов, внутренний оборот и гипотеза о назначении.",
        "kk": "<b>Қойындының мақсаты.</b> Желінің біртұтас емес екенін көрсету. "
              "Шоттар қауымдастықтарға бөлінген; әрқайсысында — көлемі, "
              "белгілі клиенттер саны, ішкі айналымы және мақсаты туралы болжам.",
        "en": "<b>What this tab is for.</b> Showing that the network is not "
              "monolithic. Accounts are split into communities, each with its "
              "size, seed count, internal turnover and a hypothesis about what "
              "it is."},
    "purpose.ask": {
        "ru": "<b>Назначение вкладки.</b> Задать вопрос о сети обычным языком "
              "вместо написания запроса. Ответ строится только из "
              "детерминированных обращений к графу, и все они показаны под "
              "ответом — проверяемо построчно.",
        "kk": "<b>Қойындының мақсаты.</b> Сұраныс жазудың орнына желі туралы "
              "қарапайым тілде сұрақ қою. Жауап тек графқа детерминделген "
              "сұраулардан құралады және олардың бәрі жауап астында "
              "көрсетілген — жолма-жол тексеруге болады.",
        "en": "<b>What this tab is for.</b> Asking a question about the network "
              "in plain language instead of writing a query. The answer is "
              "built only from deterministic graph calls, all of which are "
              "listed under it — checkable line by line."},
    "purpose.agents": {
        "ru": "<b>Назначение вкладки.</b> Доказать, что решение объяснимо. "
              "Здесь видно, что именно решали ИИ-агенты, какие пороги они "
              "выбрали и почему, что они сами считают слабым местом "
              "результата, и полный журнал их действий.",
        "kk": "<b>Қойындының мақсаты.</b> Шешімнің түсіндірілетінін дәлелдеу. "
              "Мұнда ЖИ-агенттер нені шешкені, қандай шектерді таңдағаны және "
              "неге, нәтиженің әлсіз тұсы деп өздері нені санайтыны және "
              "олардың әрекеттерінің толық журналы көрінеді.",
        "en": "<b>What this tab is for.</b> Proving the solution is explainable. "
              "It shows exactly what the AI agents decided, which thresholds "
              "they chose and why, what they themselves consider weak about the "
              "result, and a full log of their actions."},
    "purpose.data": {
        "ru": "<b>Назначение вкладки.</b> Показать, что было загружено и как "
              "распознана каждая колонка. Инструмент не требует именно трёх "
              "файлов из условия — здесь видно, как он разобрал те файлы, "
              "которые ему дали.",
        "kk": "<b>Қойындының мақсаты.</b> Не жүктелгенін және әр бағанның қалай "
              "танылғанын көрсету. Құралға шарттағы дәл үш файл қажет емес — "
              "мұнда оған берілген файлдарды қалай талдағаны көрінеді.",
        "en": "<b>What this tab is for.</b> Showing what was loaded and how each "
              "column was understood. The tool does not require the three files "
              "from the case pack — this is how it parsed the ones it was "
              "given."},
    "purpose.cost": {
        "ru": "<b>Назначение вкладки.</b> Подтвердить, что решение "
              "укладывается в ограничение по времени и что расходы на модель "
              "прозрачны: время каждого этапа, число токенов и стоимость "
              "каждого вызова.",
        "kk": "<b>Қойындының мақсаты.</b> Шешімнің уақыт шегіне сыйатынын және "
              "модель шығындарының ашық екенін растау: әр кезеңнің уақыты, "
              "токен саны және әр шақырудың құны.",
        "en": "<b>What this tab is for.</b> Confirming the solution fits the "
              "latency limit and that model spend is transparent: per-stage "
              "timing, token counts and the cost of every call."},
    "purpose.downloads": {
        "ru": "<b>Назначение вкладки.</b> Забрать три обязательные выгрузки и "
              "все вспомогательные артефакты запуска.",
        "kk": "<b>Қойындының мақсаты.</b> Үш міндетті файлды және іске қосудың "
              "барлық қосымша артефактілерін алу.",
        "en": "<b>What this tab is for.</b> Taking away the three required "
              "exports and every supporting artifact from the run."},
    "purpose.start": {
        "ru": "<b>Назначение вкладки.</b> Общая картина: сколько счетов "
              "прослежено, как распределились роли и что означает каждая.",
        "kk": "<b>Қойындының мақсаты.</b> Жалпы көрініс: қанша шот тексерілді, "
              "рөлдер қалай бөлінді және әрқайсысы нені білдіреді.",
        "en": "<b>What this tab is for.</b> The overall picture: how many "
              "accounts were traced, how the roles came out, and what each one "
              "means."},

    "prio.selected": {"ru": "Выбранный счёт", "kk": "Таңдалған шот",
                      "en": "Selected account"},
    "prio.clickhint": {
        "ru": "Ниже показан счёт №1 из списка. Нажмите любую строку таблицы "
              "выше, чтобы посмотреть другой.",
        "kk": "Төменде тізімдегі №1 шот көрсетілген. Басқасын көру үшін "
              "жоғарыдағы кестенің кез келген жолын басыңыз.",
        "en": "The account ranked #1 is shown below. Click any row in the table "
              "above to look at a different one."},
}

UI.update(_INTRO)


TAB_GUIDE = [
    ("tab.start", {
        "ru": "Общая картина и распределение ролей",
        "kk": "Жалпы көрініс және рөлдердің бөлінуі",
        "en": "The overall picture and how roles came out"}, {
        "ru": "Начать отсюда, чтобы понять масштаб",
        "kk": "Ауқымды түсіну үшін осыдан бастаңыз",
        "en": "Start here to get the scale"}),
    ("tab.priority", {
        "ru": "Ранжированный список: кого проверять первым и почему",
        "kk": "Сұрыпталған тізім: алдымен кімді тексеру керек және неге",
        "en": "The ranked list: who to review first, and why"}, {
        "ru": "Главный результат — основной сценарий работы",
        "kk": "Негізгі нәтиже — жұмыстың басты сценарийі",
        "en": "The main deliverable — the core scenario"}),
    ("tab.account", {
        "ru": "Карточка одного счёта: роль, правило, числа, карта связей",
        "kk": "Бір шоттың картасы: рөлі, ережесі, сандары, байланыс картасы",
        "en": "One account: role, rule, numbers, link map"}, {
        "ru": "Когда нужно объяснить конкретный gid",
        "kk": "Нақты gid-ті түсіндіру қажет болғанда",
        "en": "When you need to explain a specific gid"}),
    ("tab.groups", {
        "ru": "Сообщества в сети и гипотеза по каждому",
        "kk": "Желідегі қауымдастықтар және әрқайсысы бойынша болжам",
        "en": "Communities in the network, with a hypothesis each"}, {
        "ru": "Чтобы увидеть структуру, а не отдельные счета",
        "kk": "Жеке шоттарды емес, құрылымды көру үшін",
        "en": "To see structure rather than individual accounts"}),
    ("tab.ask", {
        "ru": "Вопрос о сети обычным языком",
        "kk": "Желі туралы қарапайым тілдегі сұрақ",
        "en": "A question about the network in plain language"}, {
        "ru": "Когда нужен нестандартный срез данных",
        "kk": "Деректердің стандартты емес қимасы қажет болғанда",
        "en": "When you need a cut of the data the tabs do not show"}),
    ("tab.agents", {
        "ru": "Что решали агенты, выбранные пороги, критика результата, журнал",
        "kk": "Агенттер нені шешті, таңдалған шектер, нәтиже сыны, журнал",
        "en": "What the agents decided, chosen thresholds, the critique, the log"}, {
        "ru": "Для проверки объяснимости и воспроизводимости",
        "kk": "Түсіндірілуі мен қайталанатынын тексеру үшін",
        "en": "To check explainability and reproducibility"}),
    ("tab.data", {
        "ru": "Какие файлы загружены и как распознаны колонки",
        "kk": "Қандай файлдар жүктелді және бағандар қалай танылды",
        "en": "Which files were loaded and how the columns were read"}, {
        "ru": "При запуске на своей выгрузке",
        "kk": "Өз деректеріңізде іске қосқанда",
        "en": "When running it on your own export"}),
    ("tab.cost", {
        "ru": "Время по этапам, токены, стоимость запуска",
        "kk": "Кезеңдер бойынша уақыт, токендер, іске қосу құны",
        "en": "Per-stage timing, tokens, the cost of the run"}, {
        "ru": "Для проверки ограничения в 5 минут",
        "kk": "5 минут шегін тексеру үшін",
        "en": "To verify the five-minute limit"}),
    ("tab.downloads", {
        "ru": "Три обязательные выгрузки и артефакты запуска",
        "kk": "Үш міндетті файл және іске қосу артефактілері",
        "en": "The three required exports and run artifacts"}, {
        "ru": "В конце, чтобы забрать результаты",
        "kk": "Соңында, нәтижелерді алу үшін",
        "en": "At the end, to take the results away"}),
]


UI["mt.warning"] = {
    "en": "",
    "ru": "",
    "kk": "<b>Ескерту: машиналық аударма.</b> Интерфейстің қазақ тіліндегі "
          "мәтіні машиналық аудармамен жасалған және ана тілінде сөйлейтін "
          "маман тексермеген. Мағынасы дұрыс, бірақ тіл сапасы тексеруді "
          "қажет етеді. Сандар мен атаулар барлық тілде бірдей: олар бір "
          "ереже ізінен (rule trace) қайта құрылады. Нақтылық қажет болса, "
          "ағылшын немесе орыс нұсқасын қараңыз.",
}


def machine_translation_notice(lang: str) -> str:
    """Banner shown for any language whose strings have not been reviewed."""
    if lang not in MACHINE_TRANSLATED:
        return ""
    return UI["mt.warning"].get(lang, "")


def t(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    """Look up a string. Falls back to English, then to the key itself, so a
    missing translation degrades to something readable rather than a crash."""
    entry = UI.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("en") or key
    return text.format(**fmt) if fmt else text


def role_name(role: str, lang: str = DEFAULT_LANG) -> str:
    return (ROLE_NAMES.get(role, {}).get(lang)
            or ROLE_NAMES.get(role, {}).get("en") or role)


def role_meaning(role: str, lang: str = DEFAULT_LANG) -> str:
    return (ROLE_MEANING.get(role, {}).get(lang)
            or ROLE_MEANING.get(role, {}).get("en") or "")


# ---------------------------------------------------------------------------
# localized evidence, regenerated from the rule trace
# ---------------------------------------------------------------------------

_UNITS = {
    "ru": {"m": "млн ₸", "k": "тыс. ₸", "one": "₸", "na": "н/д"},
    "kk": {"m": "млн ₸", "k": "мың ₸", "one": "₸", "na": "белгісіз"},
    "en": {"m": "M KZT", "k": "k KZT", "one": "KZT", "na": "n/a"},
}

EVIDENCE = {
    "consolidator": {
        "ru": "Получает от {in_deg} разных плательщиков{seeds}, {in_sum}; "
              "дальше уходит {fwd} — признаки точки сбора.",
        "kk": "{in_deg} түрлі төлеушіден алады{seeds}, {in_sum}; әрі қарай "
              "{fwd} кетеді — жинау нүктесінің белгілері.",
        "en": "Receives from {in_deg} distinct payers{seeds}, {in_sum}; "
              "forwards {fwd} — signs of consolidation."},
    "distributor": {
        "ru": "Рассылает {out_deg} получателям ({out_sum}) при {in_deg} "
              "плательщик(ах) — похоже на слой распределения.",
        "kk": "{out_deg} алушыға жібереді ({out_sum}), {in_deg} төлеуші бар — "
              "тарату қабатына ұқсайды.",
        "en": "Fans out to {out_deg} recipients ({out_sum}) against {in_deg} "
              "payer(s) — pattern consistent with a distribution layer."},
    "transit": {
        "ru": "Вход {in_sum} / выход {out_sum} (соотношение {ratio}) — "
              "характерно для транзита.",
        "kk": "Кіріс {in_sum} / шығыс {out_sum} (қатынас {ratio}) — транзитке тән.",
        "en": "In {in_sum} / out {out_sum} (ratio {ratio}) — pattern consistent "
              "with transit."},
    "terminal": {
        "ru": "Получает {in_sum} от {in_deg} плательщик(ов), дальше уходит "
              "{fwd}; исходящие прослежены (колено {depth}) — возможный "
              "конечный получатель.",
        "kk": "{in_deg} төлеушіден {in_sum} алады, әрі қарай {fwd} кетеді; "
              "шығыс аударымдар тексерілген ({depth}-буын) — ықтимал соңғы алушы.",
        "en": "Receives {in_sum} from {in_deg} payer(s), forwards {fwd}; "
              "outflow was traced (hop {depth}) — possible final recipient."},
    "coordinator": {
        "ru": "Деньги от {seed_reach} известных клиентов сходятся сюда через "
              "{n_key} счёт(а/ов) сбора в {n_cl} группе(ах) — кандидат на "
              "верхний уровень.",
        "kk": "{seed_reach} белгілі клиенттің ақшасы {n_cl} топтағы {n_key} "
              "жинау шоты арқылы осында жинақталады — жоғарғы деңгей үміткері.",
        "en": "Money from {seed_reach} seeds converges here via {n_key} "
              "collector account(s) across {n_cl} clusters — candidate "
              "upper-level node for review."},
    "cutoff": {
        "ru": "Счёт на {depth}-м колене: исходящие переводы не запрашивались "
              "(предел выгрузки). Получает {in_sum} от {in_deg} плательщик(ов).",
        "kk": "{depth}-буындағы шот: шығыс аударымдар сұралмаған (шолу шегі). "
              "{in_deg} төлеушіден {in_sum} алады.",
        "en": "Hop-{depth} node: onward transfers were not traced (export "
              "limit). Receives {in_sum} from {in_deg} payer(s)."},
    "peripheral": {
        "ru": "Признаков роли нет: {in_deg} плательщик(ов), {out_deg} "
              "получател(я/ей), {in_sum} вход / {out_sum} выход.",
        "kk": "Рөл белгілері жоқ: {in_deg} төлеуші, {out_deg} алушы, "
              "{in_sum} кіріс / {out_sum} шығыс.",
        "en": "No role indicators: {in_deg} payer(s), {out_deg} recipient(s), "
              "{in_sum} in / {out_sum} out."},
}

SEED_ONLY = {
    "ru": "Известный клиент; переводов выше порога выгрузки за период не "
          "обнаружено.",
    "kk": "Белгілі клиент; кезең ішінде шолу шегінен жоғары аударым табылмады.",
    "en": "Known seed; no transfers above the export threshold observed in the "
          "covered period.",
}

_SEEDS_CLAUSE = {
    "ru": " (в т.ч. {n} известных)", "kk": " ({n} белгілі)", "en": " ({n} seeds)"}


def fmt_money(x, lang: str = DEFAULT_LANG) -> str:
    u = _UNITS.get(lang, _UNITS["en"])
    try:
        x = float(x)
    except (TypeError, ValueError):
        return u["na"]
    if x != x:                                  # NaN
        return u["na"]
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f} {u['m']}"
    if abs(x) >= 1e3:
        return f"{x / 1e3:.0f} {u['k']}"
    return f"{x:,.0f} {u['one']}".replace(",", " ")


def evidence_from_trace(trace: dict, row: dict, lang: str = DEFAULT_LANG,
                        limit: int = 200) -> str:
    """Rebuild the evidence sentence in `lang` from the node's rule trace.

    The trace stores the role, the gate and the numbers the rule compared, as
    data. Rendering that into a different language is a template swap, not a
    translation: the figures are identical in all three because they come from
    the same source. No model is involved.
    """
    role = trace.get("role") or row.get("role") or "peripheral"
    m = {**(trace.get("metrics") or {})}
    for k in ("in_deg", "out_deg", "in_sum", "out_sum", "depth", "seed_reach",
              "seed_in_deg", "n_key_payers", "n_payer_clusters", "pass_ratio"):
        m.setdefault(k, row.get(k))

    def num(key, default=0):
        v = m.get(key)
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    in_sum, out_sum = m.get("in_sum") or 0, m.get("out_sum") or 0
    if role == "peripheral" and bool(row.get("is_seed")) \
            and num("in_deg") + num("out_deg") == 0:
        return SEED_ONLY.get(lang, SEED_ONLY["en"])[:limit]

    seeds_n = num("seed_in_deg")
    seeds = (_SEEDS_CLAUSE.get(lang, _SEEDS_CLAUSE["en"]).format(n=seeds_n)
             if seeds_n else "")
    try:
        share = float(out_sum) / float(in_sum) if float(in_sum) > 0 else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        share = 0.0
    ratio = m.get("pass_ratio")

    template = EVIDENCE.get(role, EVIDENCE["peripheral"])
    text = template.get(lang) or template["en"]
    rendered = text.format(
        in_deg=num("in_deg"), out_deg=num("out_deg"),
        in_sum=fmt_money(in_sum, lang), out_sum=fmt_money(out_sum, lang),
        fwd=f"{100 * min(share, 9.99):.0f}%",
        ratio=f"{float(ratio):.2f}" if isinstance(ratio, (int, float)) else "—",
        depth=num("depth"), seed_reach=num("seed_reach"),
        n_key=num("n_key_payers"), n_cl=num("n_payer_clusters"),
        seeds=seeds)
    rendered = " ".join(rendered.split())
    if len(rendered) <= limit:
        return rendered
    return rendered[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;.") + "…"


# ---------------------------------------------------------------------------
# localized `why` and cluster hypotheses
# ---------------------------------------------------------------------------

_WHY = {
    "payers":     {"ru": "получает от {n} разных плательщиков{seeds}",
                   "kk": "{n} түрлі төлеушіден алады{seeds}",
                   "en": "receives from {n} different payers{seeds}"},
    "seed_reach": {"ru": "до него дотягиваются деньги {n} известных клиентов",
                   "kk": "оған {n} белгілі клиенттің ақшасы жетеді",
                   "en": "money from {n} seeds can reach it"},
    "seed_money": {"ru": "через него проходит примерно {v} прослеженных денег",
                   "kk": "ол арқылы шамамен {v} тексерілген ақша өтеді",
                   "en": "an estimated {v} of seed-linked flow passes through"},
    "role":       {"ru": "классифицирован как «{role}»",
                   "kk": "«{role}» деп жіктелген",
                   "en": "classified {role}"},
    "cluster":    {"ru": "входит в группу {n}", "kk": "{n}-топқа кіреді",
                   "en": "sits in group {n}"},
    "forwards":   {"ru": "передаёт дальше {pct} входящих",
                   "kk": "кірістің {pct} әрі қарай жібереді",
                   "en": "forwards {pct} of inflow"},
    "untraced":   {"ru": "движение дальше не прослежено — кандидат на запрос",
                   "kk": "әрі қарайғы қозғалыс тексерілмеген — сұратуға үміткер",
                   "en": "onward flow not traced — candidate for a follow-up request"},
    "seedsuffix": {"ru": ", из них {n} известных", "kk": ", оның {n} белгілі",
                   "en": ", incl. {n} seeds"},
}

_HYP = {
    "coordinator": {
        "ru": "Возможный управляющий слой: {n} кандидат(ов) верхнего уровня, "
              "сходятся деньги {seeds} известных клиентов; выше всех {gid}.",
        "kk": "Ықтимал басқару қабаты: жоғарғы деңгейдің {n} үміткері, "
              "{seeds} белгілі клиенттің ақшасы жинақталады; ең жоғарысы {gid}.",
        "en": "Possible control layer: {n} candidate upper-level node(s), money "
              "from {seeds} seed(s) converging; {gid} ranks highest."},
    "consolidator": {
        "ru": "Признаки узла сбора: деньги {seeds} известных клиентов сходятся "
              "на счёте {gid}.",
        "kk": "Жинау түйінінің белгілері: {seeds} белгілі клиенттің ақшасы "
              "{gid} шотында жинақталады.",
        "en": "Signs of a collection hub: money from {seeds} seed(s) converges "
              "on consolidator {gid}."},
    "distributor": {
        "ru": "Похоже на слой распределения: {gid} рассылает на {out_deg} "
              "получателей внутри группы из {n} счетов.",
        "kk": "Тарату қабатына ұқсайды: {gid} {n} шоттан тұратын топ ішінде "
              "{out_deg} алушыға жібереді.",
        "en": "Pattern consistent with a distribution layer: {gid} fans out to "
              "{out_deg} recipients across a {n}-node group."},
    "transit": {
        "ru": "Транзитная цепочка: {n} сквозных счетов передают средства дальше.",
        "kk": "Транзиттік тізбек: {n} өтпелі шот қаражатты әрі қарай жібереді.",
        "en": "Transit chain: {n} pass-through accounts forward funds onward."},
    "cutoff": {
        "ru": "Группа на краю выгрузки: {n} из {total} счетов не раскрывались — "
              "дальнейшее движение неизвестно.",
        "kk": "Топ шолу шегінде: {total} шоттың {n} ашылмаған — әрі қарайғы "
              "қозғалыс белгісіз.",
        "en": "Group sits on the traversal frontier: {n} of {total} accounts "
              "were never expanded — onward flow unknown."},
    "isolated_seed": {
        "ru": "Изолированный известный клиент; переводов не обнаружено.",
        "kk": "Оқшауланған белгілі клиент; аударым табылмады.",
        "en": "Isolated known seed; no observed transfers."},
    "single": {
        "ru": "Одиночный несвязанный счёт, получено {v}.",
        "kk": "Жалғыз байланыссыз шот, {v} алынған.",
        "en": "Single disconnected node, {v} received."},
    "none": {
        "ru": "Группа из {n} счетов, известных клиентов: {seeds}, оборот внутри "
              "{v}; выраженного паттерна нет.",
        "kk": "{n} шоттан тұратын топ, белгілі клиенттер: {seeds}, ішкі "
              "айналым {v}; айқын үлгі жоқ.",
        "en": "{n}-node group, {seeds} seed(s), {v} internal turnover; no "
              "dominant role pattern detected."},
}


def why_from_row(row: dict, weights: dict, lang: str = DEFAULT_LANG,
                 limit: int = 200) -> str:
    """Rebuild the `why` sentence in `lang` from the stored score components."""
    def g(key, default=0):
        v = row.get(key, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    pairs = sorted(((name, g(f"prio_{name}_w")) for name in weights),
                   key=lambda kv: -kv[1])
    phrases: list[str] = []
    for name, value in pairs[:3]:
        if value <= 0:
            continue
        if name == "payers" and g("in_deg") > 0:
            n_seed = int(g("seed_in_deg"))
            seeds = (_WHY["seedsuffix"].get(lang, _WHY["seedsuffix"]["en"])
                     .format(n=n_seed) if n_seed else "")
            phrases.append(_WHY["payers"][lang].format(n=int(g("in_deg")), seeds=seeds))
        elif name == "seed_reach" and g("seed_reach") > 0:
            phrases.append(_WHY["seed_reach"][lang].format(n=int(g("seed_reach"))))
        elif name == "seed_money" and g("seed_kzt_attributed") > 0:
            phrases.append(_WHY["seed_money"][lang].format(
                v=fmt_money(g("seed_kzt_attributed"), lang)))
        elif name == "role":
            phrases.append(_WHY["role"][lang].format(
                role=role_name(str(row.get("role", "")), lang)))
        elif name == "cluster":
            phrases.append(_WHY["cluster"][lang].format(n=int(g("cluster_id"))))

    if row.get("outflow_observed", True) and g("in_sum") > 0:
        share = min(g("out_sum") / g("in_sum"), 9.99)
        phrases.append(_WHY["forwards"][lang].format(pct=f"{100 * share:.0f}%"))
    elif not row.get("outflow_observed", True):
        phrases.append(_WHY["untraced"][lang])

    joined = "; ".join(phrases[:4])
    text = (joined[:1].upper() + joined[1:] + ".") if joined else "—"
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;.") + "…"


def hypothesis_from_members(cluster_row: dict, members, lang: str = DEFAULT_LANG,
                            limit: int = 250) -> str:
    """Rebuild a cluster hypothesis in `lang` from its role mix and flows."""
    n = int(cluster_row.get("n_nodes", 0))
    seeds = int(cluster_row.get("n_seed", 0))
    internal = float(cluster_row.get("sum_kzt_internal", 0) or 0)
    counts = members["role"].value_counts().to_dict()

    def pick(key, **fmt):
        return _HYP[key].get(lang, _HYP[key]["en"]).format(**fmt)

    if n == 1:
        only = members.iloc[0]
        if bool(only.get("is_seed", False)):
            text = pick("isolated_seed")
        else:
            text = pick("single", v=fmt_money(float(only.get("in_sum", 0) or 0), lang))
    else:
        top = (members.nlargest(1, "priority_score").iloc[0]
               if "priority_score" in members else members.iloc[0])
        gid = int(top["gid"])
        if counts.get("coordinator"):
            text = pick("coordinator", n=counts["coordinator"], seeds=seeds, gid=gid)
        elif counts.get("consolidator"):
            text = pick("consolidator", seeds=seeds, gid=gid)
        elif counts.get("distributor"):
            text = pick("distributor", gid=gid, out_deg=int(top.get("out_deg", 0)), n=n)
        elif counts.get("transit", 0) >= 2:
            text = pick("transit", n=counts["transit"])
        elif counts.get("cutoff", 0) > n / 2:
            text = pick("cutoff", n=counts["cutoff"], total=n)
        else:
            text = pick("none", n=n, seeds=seeds, v=fmt_money(internal, lang))

    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;.") + "…"
