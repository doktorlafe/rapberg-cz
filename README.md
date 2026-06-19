# Rapberg CZ

Rapberg CZ je autorský projekt mapující cesky a prazsky rap jako kulturni, historicky a filozoficky prostor. Neni to jen sbirka textu, ale i konceptualni prochazka pameti mesta, vyvojem zanru a zpusobem, jak rap v ceskem prostredi nese hlas, konflikt, identitu a archiv doby.

## Obsah

- `lyrics/prochazka-v-metru-slov.md` - hlavni autorsky text
- `notes/concept.md` - koncept projektu a jeho smer
- `notes/symbolism.md` - motivy, skryte vyznamy a tematicke vrstvy

## Smer projektu

Projekt stavi na trech vrstvach:

1. Rap jako prochazka Prahou a jeji pameti.
2. Rap jako kronika zmen od devadesatych let po soucasnost.
3. Rap jako filozoficka forma, ktera spojuje hlas, identitu, prostor a cas.

## Mozne dalsi rozsireni

- dalsi tracky podle mest, obdobi nebo temat
- prehled historickych milniku ceskeho rapu
- vizualni koncept obalu a estetiky projektu
- anglicky preklad nebo anotovana verze textu

## Stav

Prvni verze je pripravena jako zaklad pro dalsi rozvoj a nahrani na GitHub.

## Automaticke generovani

Repo obsahuje i jednoduchy generator, ktery umi pravidelne vytvaret nove texty pres libovolne OpenAI kompatibilni API a automaticky je commitovat a pushovat do tohoto repozitare.

### Nastaveni

1. Nainstaluj zavislosti:
	`python3 --version`
2. Zkopiruj `.env.example` do `.env` nebo nastav promenne primo v shellu.
3. Ujisti se, ze mas v gitu nastaveny `user.name` a `user.email`.

Minimalni promenne:

- `RAPBERG_API_URL`
- `RAPBERG_API_AUTH_TOKEN`
- `RAPBERG_MODEL`

Volitelne promenne:

- `RAPBERG_API_AUTH_HEADER`
- `RAPBERG_API_AUTH_SCHEME`
- `RAPBERG_REQUEST_FORMAT`
- `RAPBERG_INTERVAL_SECONDS`
- `RAPBERG_OUTPUT_DIR`
- `RAPBERG_GIT_BRANCH`

Podporovane formaty requestu:

- `chat_completions` pro endpointy ve stylu `/v1/chat/completions`
- `responses` pro endpointy ve stylu `/v1/responses`

### Spusteni

Jedno vygenerovani bez pushovani:

`python3 automation/generate_and_push.py --once --dry-run`

Jedno vygenerovani s commitem a pushem:

`python3 automation/generate_and_push.py --once`

Nepretrzity rezim:

`python3 automation/generate_and_push.py`

Generator uklada nove texty do `lyrics/generated/`.

Priklad pro bezne OpenAI kompatibilni API:

`RAPBERG_API_URL=https://tvoje-api.example/v1/chat/completions`

`RAPBERG_API_AUTH_TOKEN=tvuj-token`

`RAPBERG_MODEL=tvuj-model`

`RAPBERG_REQUEST_FORMAT=chat_completions`
