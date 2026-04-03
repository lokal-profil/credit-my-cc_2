# credit-my-cc

## Description

Credit-my-CC is a web tool for producing a complaint letter when your images on Wikimedia Commons are improperly reused without proper Creative Commons attribution.

**Live tool**: <https://credit-my-cc.toolforge.org/>
**Repository**: <https://github.com/lokal-profil/credit-my-cc_2>

## How to use

1. Enter the filename of the image on Wikimedia Commons and press **Check!**.
2. Fill in the URL where the image has been improperly used.
3. Edit the attribution field if needed.
4. Choose the tone of your complaint letter (happy ☺️ / neutral 😐 / angry 😠).
5. Press **Write!** to generate the letter.
6. Copy the text and paste it into your email client.

## Setup

### Prerequisites

- Python 3.12+

### Install & run locally

```bash
git clone https://github.com/lokal-profil/credit-my-cc_2.git
cd credit-my-cc_2
```

**Using [uv](https://docs.astral.sh/uv/):**

```bash
uv sync
uv run flask --app app run --debug
```

**Using venv + pip:**

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask --app app run --debug
```

The app will be available at `http://localhost:5000`.

### Deploy with gunicorn

```bash
gunicorn app:app --bind 0.0.0.0:8000
```

### Toolforge deployment

This application is compatible with Toolforge's Python buildpack. Create a `Procfile`:

```text
web: gunicorn app:app --bind 0.0.0.0:8000
```

## Translation / i18n

### File format

Translations use the **Banana message format** — one JSON file per language in the `i18n/` directory:

```text
i18n/
├── en.json      ← English (source messages)
├── sv.json      ← Swedish
├── qqq.json     ← Message documentation (for translators)
└── <lang>.json  ← Additional languages
```

Each file looks like:

```json
{
    "@metadata": {
        "authors": ["Translator Name"]
    },
    "credit-my-cc-title": "Is someone violating your license?",
    "credit-my-cc-button-check": "Check!"
}
```

### Parameter syntax

Messages support positional parameters: `$1`, `$2`, etc.

```json
"credit-my-cc-footer-produced-for": "This page was produced for $1 by André Costa."
```

`$1` is replaced at render time with the appropriate value (e.g., a link to Wikimedia Sverige).

### Letter templates

Each complaint letter tone (happy, neutral, angry) is a **single translatable string** containing the entire letter from greeting to signature. This gives translators full control over the structure, tone, and phrasing of each letter — they are not forced into a rigid sentence-by-sentence pattern.

The letter template messages use these placeholders:

| Placeholder | Content |
| --- | --- |
| `$1` | Description fragment (e.g. " of a sunset"), may be empty |
| `$2` | URL where the image is improperly used |
| `$3` | Upload date fragment (e.g. " since 2024-01-15"), may be empty |
| `$4` | URL to the original file on Wikimedia Commons |
| `$5` | How the author wants to be credited (may contain HTML) |
| `$6` | License name (e.g. "CC BY-SA 4.0") |
| `$7` | URL to the license text |
| `$8` | File title on Commons |
| `$9` | Example online attribution (HTML) |
| `$10` | Example print/offline attribution (plain text) |

## Development

### Running tests and linting

Install dev dependencies (`uv sync --extra dev` or `pip install -e ".[dev]"`), then run:

```bash
pytest                 # tests
ruff check .           # lint
ruff format --check .  # formatting
mypy app.py            # type checking
```

> If using uv, prefix commands with `uv run` (e.g. `uv run pytest`).

### CI

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs lint, type checking, and tests automatically on every push to `main` and on pull requests.

## Background

This is a modern Python/Flask rewrite of the [original static jQuery tool (v1)](https://github.com/Wikimedia-Sverige/credit-my-cc) by André Costa for Wikimedia Sverige.

### Key improvements over the original

- **Python/Flask backend** — modern framework, easy to deploy on Toolforge or any WSGI host.
- **Translatewiki.net-compatible i18n** — uses the [Banana message format](https://github.com/wikimedia/banana-i18n) via [`banana-i18n`](https://pypi.org/project/banana-i18n/), the same format used by MediaWiki and other Wikimedia tools. Translation files in `i18n/` are ready to be synced with [translatewiki.net](https://translatewiki.net/wiki/Translating:Intuition).
- **No jQuery dependency** — vanilla JavaScript.
- **Responsive design** — works on mobile and desktop.
- **Server-side letter rendering** — letters are rendered through Jinja2 templates with full i18n support, making it easy to add new letter templates or tones.

## Contributing

We would love to see more complaint letter templates, support for additional languages, and design improvements.

By contributing you agree that your work is released under the [MIT license](LICENSE).

## License

Credit-my-CC is licensed under the [MIT license](LICENSE).

## Credits

- Initial letters by [Jan Ainali](https://github.com/ainali).
- Original tool by André Costa for [Wikimedia Sverige](https://wikimedia.se/).
- Logo uses elements from the [BY icon](https://creativecommons.org/about/downloads#Icons) by Creative Commons ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)) and [Speech bubble](https://commons.wikimedia.org/wiki/File:Speech_bubble.svg) by Amada44 (Public Domain).
- Edit icon from the [Wikimedia Codex](https://www.mediawiki.org/wiki/Codex) design system ([MIT](https://gerrit.wikimedia.org/r/plugins/gitiles/design/codex/+/refs/heads/main/packages/codex-icons/LICENSE)).
