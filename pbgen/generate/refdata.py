"""Closed code sets for the fixed reference tables (FR-021 allows fixed lists for these).

Currency names and symbols come from Faker's currency provider; the ISO numeric codes,
the 250 ISO 3166 countries (249 official + XK Kosovo), account types, transaction types and
merchant category groups are defined here.
"""

from __future__ import annotations

from faker.providers.currency import Provider as _CurrencyProvider

# 40 most-traded currencies, USD first (CurrencyId = position + 1). code -> (ISO numeric, minor units)
CURRENCY_CODES = [
    ("USD", 840, 2), ("EUR", 978, 2), ("JPY", 392, 0), ("GBP", 826, 2), ("CNY", 156, 2), ("AUD", 36, 2),
    ("CAD", 124, 2), ("CHF", 756, 2), ("HKD", 344, 2), ("SGD", 702, 2), ("SEK", 752, 2), ("KRW", 410, 0),
    ("NOK", 578, 2), ("NZD", 554, 2), ("INR", 356, 2), ("MXN", 484, 2), ("TWD", 901, 2), ("ZAR", 710, 2),
    ("BRL", 986, 2), ("DKK", 208, 2), ("PLN", 985, 2), ("THB", 764, 2), ("ILS", 376, 2), ("IDR", 360, 2),
    ("CZK", 203, 2), ("AED", 784, 2), ("TRY", 949, 2), ("HUF", 348, 2), ("CLP", 152, 0), ("SAR", 682, 2),
    ("PHP", 608, 2), ("MYR", 458, 2), ("COP", 170, 2), ("RUB", 643, 2), ("RON", 946, 2), ("PEN", 604, 2),
    ("BHD", 48, 3), ("BGN", 975, 2), ("ARS", 32, 2), ("EGP", 818, 2),
]
_NAMES = dict(_CurrencyProvider.currencies)
_SYMBOLS = _CurrencyProvider.currency_symbols
CURRENCIES = [(code, _NAMES.get(code, code), num, minor, _SYMBOLS.get(code, code)) for code, num, minor in CURRENCY_CODES]
CURRENCY_SET = {c[0] for c in CURRENCIES}

_EURO = "AD AT BE CY DE EE ES FI FR GR HR IE IT LT LU LV MC ME MT NL PT SI SK SM VA XK".split()
_OWN = {"JP": "JPY", "GB": "GBP", "CN": "CNY", "AU": "AUD", "CA": "CAD", "CH": "CHF", "LI": "CHF", "HK": "HKD",
        "SG": "SGD", "SE": "SEK", "KR": "KRW", "NO": "NOK", "NZ": "NZD", "IN": "INR", "MX": "MXN", "TW": "TWD",
        "ZA": "ZAR", "BR": "BRL", "DK": "DKK", "PL": "PLN", "TH": "THB", "IL": "ILS", "ID": "IDR", "CZ": "CZK",
        "AE": "AED", "TR": "TRY", "HU": "HUF", "CL": "CLP", "SA": "SAR", "PH": "PHP", "MY": "MYR", "CO": "COP",
        "RU": "RUB", "RO": "RON", "PE": "PEN", "BH": "BHD", "BG": "BGN", "AR": "ARS", "EG": "EGP"}

_COUNTRIES = """AD Andorra|AE United Arab Emirates|AF Afghanistan|AG Antigua and Barbuda|AI Anguilla|AL Albania|AM Armenia|
AO Angola|AQ Antarctica|AR Argentina|AS American Samoa|AT Austria|AU Australia|AW Aruba|AX Aland Islands|AZ Azerbaijan|
BA Bosnia and Herzegovina|BB Barbados|BD Bangladesh|BE Belgium|BF Burkina Faso|BG Bulgaria|BH Bahrain|BI Burundi|
BJ Benin|BL Saint Barthelemy|BM Bermuda|BN Brunei Darussalam|BO Bolivia|BQ Bonaire, Sint Eustatius and Saba|BR Brazil|
BS Bahamas|BT Bhutan|BV Bouvet Island|BW Botswana|BY Belarus|BZ Belize|CA Canada|CC Cocos (Keeling) Islands|
CD Congo, Democratic Republic of the|CF Central African Republic|CG Congo|CH Switzerland|CI Cote d'Ivoire|CK Cook Islands|
CL Chile|CM Cameroon|CN China|CO Colombia|CR Costa Rica|CU Cuba|CV Cabo Verde|CW Curacao|CX Christmas Island|CY Cyprus|
CZ Czechia|DE Germany|DJ Djibouti|DK Denmark|DM Dominica|DO Dominican Republic|DZ Algeria|EC Ecuador|EE Estonia|
EG Egypt|EH Western Sahara|ER Eritrea|ES Spain|ET Ethiopia|FI Finland|FJ Fiji|FK Falkland Islands (Malvinas)|
FM Micronesia|FO Faroe Islands|FR France|GA Gabon|GB United Kingdom|GD Grenada|GE Georgia|GF French Guiana|GG Guernsey|
GH Ghana|GI Gibraltar|GL Greenland|GM Gambia|GN Guinea|GP Guadeloupe|GQ Equatorial Guinea|GR Greece|
GS South Georgia and the South Sandwich Islands|GT Guatemala|GU Guam|GW Guinea-Bissau|GY Guyana|HK Hong Kong|
HM Heard Island and McDonald Islands|HN Honduras|HR Croatia|HT Haiti|HU Hungary|ID Indonesia|IE Ireland|IL Israel|
IM Isle of Man|IN India|IO British Indian Ocean Territory|IQ Iraq|IR Iran|IS Iceland|IT Italy|JE Jersey|JM Jamaica|
JO Jordan|JP Japan|KE Kenya|KG Kyrgyzstan|KH Cambodia|KI Kiribati|KM Comoros|KN Saint Kitts and Nevis|KP North Korea|
KR South Korea|KW Kuwait|KY Cayman Islands|KZ Kazakhstan|LA Lao People's Democratic Republic|LB Lebanon|LC Saint Lucia|
LI Liechtenstein|LK Sri Lanka|LR Liberia|LS Lesotho|LT Lithuania|LU Luxembourg|LV Latvia|LY Libya|MA Morocco|MC Monaco|
MD Moldova|ME Montenegro|MF Saint Martin (French part)|MG Madagascar|MH Marshall Islands|MK North Macedonia|ML Mali|
MM Myanmar|MN Mongolia|MO Macao|MP Northern Mariana Islands|MQ Martinique|MR Mauritania|MS Montserrat|MT Malta|
MU Mauritius|MV Maldives|MW Malawi|MX Mexico|MY Malaysia|MZ Mozambique|NA Namibia|NC New Caledonia|NE Niger|
NF Norfolk Island|NG Nigeria|NI Nicaragua|NL Netherlands|NO Norway|NP Nepal|NR Nauru|NU Niue|NZ New Zealand|OM Oman|
PA Panama|PE Peru|PF French Polynesia|PG Papua New Guinea|PH Philippines|PK Pakistan|PL Poland|PM Saint Pierre and Miquelon|
PN Pitcairn|PR Puerto Rico|PS Palestine|PT Portugal|PW Palau|PY Paraguay|QA Qatar|RE Reunion|RO Romania|RS Serbia|
RU Russian Federation|RW Rwanda|SA Saudi Arabia|SB Solomon Islands|SC Seychelles|SD Sudan|SE Sweden|SG Singapore|
SH Saint Helena, Ascension and Tristan da Cunha|SI Slovenia|SJ Svalbard and Jan Mayen|SK Slovakia|SL Sierra Leone|
SM San Marino|SN Senegal|SO Somalia|SR Suriname|SS South Sudan|ST Sao Tome and Principe|SV El Salvador|
SX Sint Maarten (Dutch part)|SY Syrian Arab Republic|SZ Eswatini|TC Turks and Caicos Islands|TD Chad|
TF French Southern Territories|TG Togo|TH Thailand|TJ Tajikistan|TK Tokelau|TL Timor-Leste|TM Turkmenistan|TN Tunisia|
TO Tonga|TR Turkiye|TT Trinidad and Tobago|TV Tuvalu|TW Taiwan|TZ Tanzania|UA Ukraine|UG Uganda|
UM United States Minor Outlying Islands|US United States|UY Uruguay|UZ Uzbekistan|VA Holy See|
VC Saint Vincent and the Grenadines|VE Venezuela|VG Virgin Islands (British)|VI Virgin Islands (U.S.)|VN Viet Nam|
VU Vanuatu|WF Wallis and Futuna|WS Samoa|XK Kosovo|YE Yemen|YT Mayotte|ZA South Africa|ZM Zambia|ZW Zimbabwe"""

_PREFIX = {"US": "+1", "CA": "+1", "PR": "+1", "MX": "+52", "GB": "+44", "DE": "+49", "FR": "+33", "ES": "+34",
           "IT": "+39", "JP": "+81", "CN": "+86", "IN": "+91", "BR": "+55", "AU": "+61"}

COUNTRIES = []
for _entry in _COUNTRIES.replace("\n", "").split("|"):
    _code, _name = _entry.split(" ", 1)
    _cur = "EUR" if _code in _EURO else _OWN.get(_code, "USD")
    COUNTRIES.append((_code, _name, _cur, _PREFIX.get(_code, "")))
assert len(COUNTRIES) == 250, len(COUNTRIES)
assert all(c[2] in CURRENCY_SET for c in COUNTRIES)

# 24 account types: code, name, category, term months, base rate, min balance, monthly fee, overdraft allowed
ACCOUNT_TYPES = [
    ("CHKBASIC", "Basic Checking", "CHECKING", 0, 0.01, 0, 5, True),
    ("CHKFREE", "Free Checking", "CHECKING", 0, 0.00, 0, 0, True),
    ("CHKPLUS", "Checking Plus", "CHECKING", 0, 0.05, 1500, 12, True),
    ("CHKPREM", "Premier Checking", "CHECKING", 0, 0.10, 10000, 25, True),
    ("CHKSTUD", "Student Checking", "CHECKING", 0, 0.00, 0, 0, False),
    ("CHKSENR", "Senior Checking", "CHECKING", 0, 0.05, 0, 0, True),
    ("CHKBUS", "Business Checking", "CHECKING", 0, 0.02, 2500, 15, True),
    ("CHKBUSPL", "Business Checking Plus", "CHECKING", 0, 0.08, 25000, 30, True),
    ("SAVBASIC", "Basic Savings", "SAVINGS", 0, 0.25, 300, 3, False),
    ("SAVHIYLD", "High-Yield Savings", "SAVINGS", 0, 3.80, 1000, 0, False),
    ("SAVKIDS", "Kids Savings", "SAVINGS", 0, 1.00, 0, 0, False),
    ("SAVGOAL", "Goal Savings", "SAVINGS", 0, 2.50, 100, 0, False),
    ("SAVBUS", "Business Savings", "SAVINGS", 0, 1.50, 5000, 5, False),
    ("SAVHOL", "Holiday Club", "SAVINGS", 0, 0.50, 0, 0, False),
    ("MMSTD", "Money Market", "MONEYMARKET", 0, 3.10, 2500, 10, False),
    ("MMPREM", "Premier Money Market", "MONEYMARKET", 0, 4.05, 25000, 0, False),
    ("MMBUS", "Business Money Market", "MONEYMARKET", 0, 3.60, 10000, 15, False),
    ("CD3M", "3-Month CD", "CD", 3, 3.50, 500, 0, False),
    ("CD6M", "6-Month CD", "CD", 6, 4.10, 500, 0, False),
    ("CD12M", "12-Month CD", "CD", 12, 4.40, 500, 0, False),
    ("CD18M", "18-Month CD", "CD", 18, 4.25, 1000, 0, False),
    ("CD24M", "24-Month CD", "CD", 24, 4.00, 1000, 0, False),
    ("CD36M", "36-Month CD", "CD", 36, 3.85, 1000, 0, False),
    ("CD60M", "60-Month CD", "CD", 60, 3.70, 1000, 0, False),
]
CHECKING_TYPE_IDS = [i + 1 for i, t in enumerate(ACCOUNT_TYPES) if t[2] == "CHECKING"]
SAVINGS_TYPE_IDS = [i + 1 for i, t in enumerate(ACCOUNT_TYPES) if t[2] == "SAVINGS"]
OTHER_TYPE_IDS = [i + 1 for i, t in enumerate(ACCOUNT_TYPES) if t[2] in ("MONEYMARKET", "CD")]

# 60 transaction types: code, description, direction, channel, is-fee
_TT = [
    ("POS", "Point-of-sale purchase", "D", "POS", False), ("POSCB", "Point-of-sale purchase with cash back", "D", "POS", False),
    ("ECOM", "Online card purchase", "D", "POS", False), ("CONTLS", "Contactless card purchase", "D", "POS", False),
    ("RECUR", "Recurring card payment", "D", "POS", False), ("ATMWD", "ATM withdrawal", "D", "ATM", False),
    ("ATMWDF", "ATM withdrawal, foreign", "D", "ATM", False), ("ATMXFR", "ATM transfer out", "D", "ATM", False),
    ("ACHDB", "ACH debit", "D", "ACH", False), ("ACHBILL", "ACH bill payment", "D", "ACH", False),
    ("ACHLOAN", "ACH loan payment", "D", "ACH", False), ("ACHTAX", "ACH tax payment", "D", "ACH", False),
    ("ACHINS", "ACH insurance premium", "D", "ACH", False), ("ACHUTIL", "ACH utility payment", "D", "ACH", False),
    ("WIREOUT", "Outgoing wire", "D", "WIRE", False), ("WIREINT", "Outgoing international wire", "D", "WIRE", False),
    ("XFER", "Transfer to another account", "D", "ONLINE", False), ("LOANPMT", "Loan payment", "D", "INTERNAL", False),
    ("CHKPAID", "Check paid", "D", "BRANCH", False), ("CASHWD", "Teller cash withdrawal", "D", "BRANCH", False),
    ("BILLPAY", "Online bill payment", "D", "ONLINE", False), ("P2POUT", "Person-to-person payment sent", "D", "ONLINE", False),
    ("FEEMNT", "Monthly maintenance fee", "D", "INTERNAL", True), ("FEEOD", "Overdraft fee", "D", "INTERNAL", True),
    ("FEENSF", "Insufficient funds fee", "D", "INTERNAL", True), ("FEEATM", "ATM fee", "D", "INTERNAL", True),
    ("FEEWIRE", "Wire transfer fee", "D", "INTERNAL", True), ("FEEFX", "Foreign transaction fee", "D", "INTERNAL", True),
    ("FEESTMT", "Paper statement fee", "D", "INTERNAL", True), ("FEESTOP", "Stop payment fee", "D", "INTERNAL", True),
    ("FEECARD", "Card replacement fee", "D", "INTERNAL", True), ("DBADJ", "Debit adjustment", "D", "INTERNAL", False),
    ("PAYROLL", "Payroll direct deposit", "C", "ACH", False), ("ACHCR", "ACH credit", "C", "ACH", False),
    ("ACHGOV", "Government benefit", "C", "ACH", False), ("ACHTAXR", "Tax refund", "C", "ACH", False),
    ("ACHPENS", "Pension payment", "C", "ACH", False), ("WIREIN", "Incoming wire", "C", "WIRE", False),
    ("WIREINTI", "Incoming international wire", "C", "WIRE", False), ("XFERIN", "Transfer from another account", "C", "ONLINE", False),
    ("DEPCASH", "Cash deposit", "C", "BRANCH", False), ("DEPCHK", "Check deposit", "C", "BRANCH", False),
    ("DEPMOB", "Mobile check deposit", "C", "ONLINE", False), ("DEPATM", "ATM deposit", "C", "ATM", False),
    ("INTPAID", "Interest paid", "C", "INTERNAL", False), ("REFUND", "Merchant refund", "C", "POS", False),
    ("P2PIN", "Person-to-person payment received", "C", "ONLINE", False), ("REVFEE", "Fee reversal", "C", "INTERNAL", False),
    ("CRADJ", "Credit adjustment", "C", "INTERNAL", False), ("DIVID", "Dividend credit", "C", "ACH", False),
    ("RWDS", "Rewards redemption", "C", "INTERNAL", False), ("CBACK", "Chargeback credit", "C", "INTERNAL", False),
    ("LOANDSB", "Loan disbursement", "C", "INTERNAL", False), ("CDMAT", "CD maturity credit", "C", "INTERNAL", False),
    ("ZELLEIN", "Instant payment received", "C", "ONLINE", False), ("VENMOIN", "Wallet transfer in", "C", "ONLINE", False),
    ("ACHSAL", "Salary advance", "C", "ACH", False), ("INSCLM", "Insurance claim payment", "C", "ACH", False),
    ("GRANT", "Grant payment", "C", "ACH", False), ("MISCCR", "Miscellaneous credit", "C", "INTERNAL", False),
]
TRANSACTION_TYPES = _TT
TT_ID = {t[0]: i + 1 for i, t in enumerate(_TT)}
assert len(TRANSACTION_TYPES) == 60

# Debit type mix for "other" debits (not transfers / loan payments / POS): code, weight
OTHER_DEBIT_TYPES = [("ACHDB", 3), ("ACHBILL", 3), ("ACHUTIL", 1), ("ATMWD", 4), ("FEEMNT", 1), ("FEEOD", 0.5),
                     ("FEEATM", 0.5), ("CHKPAID", 1), ("BILLPAY", 1), ("P2POUT", 1), ("WIREOUT", 0.2),
                     ("CASHWD", 0.3), ("DBADJ", 0.1)]
POS_TYPES = [("POS", 6), ("ECOM", 2), ("CONTLS", 2), ("RECUR", 1), ("POSCB", 0.3)]
OTHER_CREDIT_TYPES = [("ACHCR", 3), ("DEPMOB", 2), ("DEPCHK", 1), ("DEPCASH", 1), ("P2PIN", 2), ("INTPAID", 1),
                      ("REFUND", 1), ("ACHGOV", 0.5), ("WIREIN", 0.2), ("ACHTAXR", 0.3), ("MISCCR", 0.2)]

# Merchant category groups (synthetic MCC codes spread over the real MCC ranges)
MCC_GROUPS = [
    ("Airlines", 3000, 3299, 40), ("Car Rental", 3351, 3441, 20), ("Lodging", 3501, 3999, 40),
    ("Transportation", 4000, 4799, 40), ("Utilities", 4800, 4999, 30), ("Wholesale", 5000, 5199, 30),
    ("Grocery", 5200, 5499, 30), ("Automotive", 5500, 5599, 30), ("Apparel", 5600, 5699, 30),
    ("Home Furnishing", 5700, 5799, 30), ("Restaurants", 5800, 5899, 30), ("Retail", 5900, 5999, 40),
    ("Financial", 6000, 6399, 20), ("Personal Services", 7000, 7299, 30), ("Business Services", 7300, 7399, 30),
    ("Repair Services", 7500, 7699, 20), ("Entertainment", 7800, 7999, 30), ("Medical", 8000, 8099, 30),
    ("Professional Services", 8100, 8999, 30), ("Government", 9000, 9999, 20),
]
assert sum(g[3] for g in MCC_GROUPS) == 600
