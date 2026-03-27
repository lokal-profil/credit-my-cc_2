"""
Credit-my-CC — Flask application.

A tool for producing complaint letters when your Creative Commons
licensed images on Wikimedia Commons are improperly reused.

Migrated from the original static jQuery application by André Costa
for Wikimedia Sverige to a Python/Flask application with translatewiki.net
compatible i18n support using the Banana message format.
"""

import functools
import re
from pathlib import Path
from urllib.parse import unquote

import requests
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
)
from banana_i18n import BananaI18n
from markupsafe import Markup

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

I18N_DIR = Path(__file__).resolve().parent / "i18n"
banana = BananaI18n(I18N_DIR)

# ---------------------------------------------------------------------------
# Helpers: discover available languages from i18n/ directory
# ---------------------------------------------------------------------------

# Language display names (extend as translations are added)
LANGUAGE_AUTONYMS = {
    "en": "English",
    "sv": "Svenska",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pt": "Português",
    "nl": "Nederlands",
    "fi": "Suomi",
    "da": "Dansk",
    "nb": "Norsk bokmål",
    "nn": "Norsk nynorsk",
    "pl": "Polski",
    "it": "Italiano",
}


@functools.cache
def _available_languages():
    """Return a sorted list of language codes with translations."""
    langs = []
    for f in I18N_DIR.iterdir():
        if f.suffix == ".json" and f.stem not in ("qqq",):
            langs.append(f.stem)
    return sorted(langs)


def _get_language():
    """Determine the current interface language."""
    # 1. Explicit ?lang= parameter
    lang = request.args.get("lang")
    if lang and lang in _available_languages():
        return lang
    # 2. Accept-Language header
    best = request.accept_languages.best_match(
        _available_languages(), default="en"
    )
    return best


@app.context_processor
def inject_i18n_helpers():
    """Make translation helpers and language info available in templates."""
    lang = _get_language()

    available = _available_languages()
    lang_choices = [
        (code, LANGUAGE_AUTONYMS.get(code, code)) for code in available
    ]

    def msg(key, *args):
        """Translate message *key*, replacing $1, $2, … with *args*."""
        text = banana.translate(lang, key)
        for i in range(len(args), 0, -1):
            text = text.replace(f"${i}", str(args[i - 1]))
        return Markup(text)

    return dict(
        _=msg,
        current_lang=lang,
        lang_choices=lang_choices,
        filename_placeholder=FILENAME_PLACEHOLDER,
    )


# ---------------------------------------------------------------------------
# Example files – same ones as the original tool
# ---------------------------------------------------------------------------

EXAMPLES = [
    {
        "label_key": "credit-my-cc-example-easy",
        "filename": "Sempervivum x funckii, RBGE 2010, 2.jpg",
    },
    {
        "label_key": "credit-my-cc-example-multiple-creators",
        "filename": "Foo.svg",
    },
    {
        "label_key": "credit-my-cc-example-pd",
        "filename": "Globen.jpg",
    },
    {
        "label_key": "credit-my-cc-example-cc0",
        "filename": "Well-wikipedia2.svg",
    },
    {
        "label_key": "credit-my-cc-example-gfdl",
        "filename": "0038-fahrradsammlung-RalfR.jpg",
    },
    {
        "label_key": "credit-my-cc-example-no-license",
        "filename": '"A_Basket full of Wool" (6360159381).jpg',
    },
    {
        "label_key": "credit-my-cc-example-no-info-template",
        "filename": "Ruins_at_Delfi.JPG",
    },
]

# ---------------------------------------------------------------------------
# Commons API helpers
# ---------------------------------------------------------------------------

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "CreditMyCC/2.0 (https://lp-tools.toolforge.org/credit-my-cc_2/; User:Lokal_Profil)"
THUMB_SIZE = 600
FILENAME_PLACEHOLDER = "Foo.svg"
VALID_TONES = {"happy", "neutral", "angry"}


def _strip_html(html_str):
    """Remove all HTML tags from *html_str*."""
    return re.sub(r"<[^>]+>", "", html_str)


def _query_commons(filename):
    """Query the Wikimedia Commons API for file metadata."""
    params = {
        "action": "query",
        "prop": "imageinfo",
        "format": "json",
        "iilimit": "1",
        "iiprop": "url|timestamp|extmetadata",
        "iiurlwidth": str(THUMB_SIZE),
        "iiextmetadatafilter": "Credit|ImageDescription|Artist|"
        "LicenseShortName|UsageTerms|LicenseUrl|Copyrighted",
        "titles": f"File:{filename}",
    }
    resp = requests.get(
        COMMONS_API, params=params, timeout=15,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.json()


def _parse_commons_response(data):
    """Parse the JSON response from the Commons API.

    Returns a dict with either an ``error`` key or the parsed metadata.
    """
    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if "missing" in page:
            return {"error": "missing_file"}

        ii = page.get("imageinfo", [{}])[0]
        ext = ii.get("extmetadata", {})

        result = {
            "thumb_url": ii.get("thumburl", ""),
            "description_url": ii.get("descriptionurl", ""),
            "file_title": page.get("title", "")[5:],  # strip "File:"
        }

        # -- Public domain check
        copyrighted = ext.get("Copyrighted", {}).get("value", "")
        if copyrighted == "False":
            return {**result, "error": "public_domain"}

        # -- License
        lic_url = ext.get("LicenseUrl", {}).get("value", "")
        lic_short = ext.get("LicenseShortName", {}).get("value", "")

        if not lic_url or not lic_short:
            return {**result, "error": "no_license"}

        # Normalise license name
        render = False
        if lic_short.startswith("CC-BY-SA-") or lic_short.startswith(
            "CC BY-SA "
        ):
            lic_short = "CC BY-SA " + lic_short[9:]
            render = True
        elif lic_short.startswith("CC-BY-") or lic_short.startswith(
            "CC BY "
        ):
            lic_short = "CC BY " + lic_short[6:]
            render = True
        elif lic_short.startswith("CC0"):
            return {**result, "error": "cc0"}
        else:
            return {**result, "error": "unsupported_license"}

        # Missing metadata check
        artist = ext.get("Artist", {}).get("value", "")
        credit = ext.get("Credit", {}).get("value", "")
        img_desc = ext.get("ImageDescription", {}).get("value", "")

        if not (artist and credit and img_desc):
            return {**result, "error": "no_information"}

        if render:
            result.update(
                {
                    "license_title": lic_short,
                    "license_url": lic_url,
                    "credit": artist,
                    "credit_extra": credit,
                    "description_extra": _strip_html(img_desc),
                    "upload_date": ii.get("timestamp", "")[:10],
                }
            )
            return result

    return {"error": "missing_file"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Main page."""
    return render_template("index.html", examples=EXAMPLES)


@app.route("/api/lookup")
def api_lookup():
    """AJAX endpoint: look up a filename on Commons."""
    filename = request.args.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "missing_file"}), 400

    # Clean up input – handle URLs, File: prefixes, etc.
    if re.search(r"[^.]*\.wiki(p|m)edia\.org/wiki/", filename, re.I):
        try:
            filename = unquote(filename.split("/wiki/")[1].split(":")[1])
            filename = filename.replace("_", " ")
        except (IndexError, KeyError):
            return jsonify({"error": "random_url"}), 400
    elif "://" in filename:
        return jsonify({"error": "random_url"}), 400
    elif ":" in filename:
        filename = filename.split(":")[1]

    try:
        raw = _query_commons(filename)
    except requests.RequestException:
        return jsonify({"error": "api_error"}), 502

    result = _parse_commons_response(raw)
    return jsonify(result)


@app.route("/api/letter")
def api_letter():
    """AJAX endpoint: render a complaint letter."""
    tone = request.args.get("tone", "happy")
    if tone not in VALID_TONES:
        return jsonify({"error": "invalid_tone"}), 400
    lang = _get_language()

    # Gather data from query parameters
    data = {
        "credit": request.args.get("credit", ""),
        "descr": request.args.get("descr", ""),
        "file_url": request.args.get("file_url", ""),
        "file_title": request.args.get("file_title", ""),
        "license_title": request.args.get("license_title", ""),
        "license_url": request.args.get("license_url", ""),
        "upload_date": request.args.get("upload_date", ""),
        "usage": request.args.get("usage", ""),
    }

    # Build description / date fragments
    descr_fragment = ""
    if data["descr"]:
        descr_fragment = banana.translate(
            lang, "credit-my-cc-of-object"
        ).replace("$1", data["descr"])

    date_fragment = ""
    if data["upload_date"]:
        date_fragment = banana.translate(
            lang, "credit-my-cc-since-date"
        ).replace("$1", data["upload_date"])

    # Build example attribution lines
    example_online = (
        f'<a href="{data["file_url"]}">{data["file_title"]}</a> / '
        f'<span>{data["credit"]}</span> / '
        f'<a href="{data["license_url"]}">{data["license_title"]}</a>'
    )
    example_offline = (
        f'{data["file_title"]} @ Wikimedia Commons / '
        f'{_strip_html(data["credit"])} / '
        f'{data["license_title"]}'
    )

    # Look up the single letter template for this tone
    msg_key = f"credit-my-cc-letter-template-{tone}"
    letter_html = banana.translate(lang, msg_key)
    if letter_html is None:
        letter_html = banana.translate("en", msg_key) or ""

    # Replace all $N placeholders with the actual values
    # $1  = description fragment      $6  = license title
    # $2  = usage URL                 $7  = license URL
    # $3  = date fragment             $8  = file title
    # $4  = file URL (Commons)        $9  = example online
    # $5  = credit / attribution      $10 = example offline
    #
    # Replace $10 before $1 to avoid partial match.
    replacements = [
        ("$10", example_offline),
        ("$1", descr_fragment),
        ("$2", data["usage"]),
        ("$3", date_fragment),
        ("$4", data["file_url"]),
        ("$5", data["credit"]),
        ("$6", data["license_title"]),
        ("$7", data["license_url"]),
        ("$8", data["file_title"]),
        ("$9", example_online),
    ]
    for placeholder, value in replacements:
        letter_html = letter_html.replace(placeholder, value)

    return letter_html


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
