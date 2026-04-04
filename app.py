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
from urllib.parse import unquote, urlparse

import nh3
import requests
from banana_i18n import BananaI18n
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
)
from markupsafe import Markup, escape

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

I18N_DIR = Path(__file__).resolve().parent / "i18n"
LETTERS_DIR = Path(__file__).resolve().parent / "letters"
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


def _discover_all_other_letters():
    """Scan letters/{lang}/*.html and return cached metadata + content.

    Returns a dict mapping language codes to lists of letter dicts:
    ``{lang: [{"slug": ..., "title": ..., "author": ..., "html": ...}]}``.

    The slug (filename stem) is used as the tone parameter value in the
    /api/letter endpoint, avoiding exposing filesystem paths to the client.
    """
    result = {}
    if not LETTERS_DIR.is_dir():
        return result
    for lang_dir in sorted(LETTERS_DIR.iterdir()):
        if not lang_dir.is_dir():
            continue
        lang = lang_dir.name
        letters = []
        for f in sorted(lang_dir.glob("*.html")):
            content = f.read_text(encoding="utf-8")
            title = f.stem
            author = ""
            html_lines = []
            for line in content.splitlines():
                stripped = line.strip()
                if not html_lines and stripped.startswith("<!--") and stripped.endswith("-->"):
                    if stripped.startswith("<!-- title:"):
                        title = stripped[len("<!-- title:") :][: -len("-->")].strip()
                    elif stripped.startswith("<!-- author:"):
                        author = stripped[len("<!-- author:") :][: -len("-->")].strip()
                    continue
                html_lines.append(line)
            letters.append(
                {
                    "slug": f.stem,
                    "title": title,
                    "author": author,
                    "html": "\n".join(html_lines),
                }
            )
        if letters:
            result[lang] = letters
    return result


OTHER_LETTERS = _discover_all_other_letters()


def _get_language():
    """Determine the current interface language."""
    # 1. Explicit ?lang= parameter
    lang = request.args.get("lang")
    if lang and lang in _available_languages():
        return lang
    # 2. Accept-Language header
    best = request.accept_languages.best_match(_available_languages(), default="en")
    return best


@app.context_processor
def inject_i18n_helpers():
    """Make translation helpers and language info available in templates."""
    lang = _get_language()

    available = _available_languages()
    lang_choices = [(code, LANGUAGE_AUTONYMS.get(code, code)) for code in available]

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
        other_letters=OTHER_LETTERS.get(lang, []),
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
        "label": "CC0",
        "filename": "Well-wikipedia2.svg",
    },
    {
        "label": "GFDL",
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
USER_AGENT = "CreditMyCC/2.0 (https://credit-my-cc.toolforge.org/; User:Lokal_Profil)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
THUMB_SIZE = 600
FILENAME_PLACEHOLDER = "Foo.svg"
VALID_TONES = {"happy", "neutral", "angry"}


def _strip_html(html_str):
    """Remove all HTML tags from *html_str*."""
    return nh3.clean(html_str, tags=set())


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
    resp = _session.get(
        COMMONS_API,
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_commons_response(data):
    """Parse the JSON response from the Commons API.

    Returns a dict with either an ``error`` key or the parsed metadata.
    """
    pages = data.get("query", {}).get("pages", {})
    for _page_id, page in pages.items():
        if "missing" in page:
            return {"error": "missing_file"}

        ii = page.get("imageinfo", [{}])[0]
        ext = ii.get("extmetadata", {})

        result = {
            "thumb_url": ii.get("thumburl", ""),
            "description_url": ii.get("descriptionurl", ""),
            "file_title": page.get("title", "").removeprefix("File:"),
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
        if lic_short.startswith("CC-BY-SA-") or lic_short.startswith("CC BY-SA "):
            lic_short = "CC BY-SA " + lic_short[9:]
            render = True
        elif lic_short.startswith("CC-BY-") or lic_short.startswith("CC BY "):
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
            path = unquote(urlparse(filename).path)
            wiki_page = path.split("/wiki/", 1)[1]
            filename = wiki_page.split(":", 1)[1].replace("_", " ")
        except (IndexError, ValueError):
            return jsonify({"error": "random_url"}), 400
    elif "://" in filename:
        return jsonify({"error": "random_url"}), 400
    elif ":" in filename:
        filename = filename.split(":", 1)[1]

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
    lang = _get_language()

    # Gather raw data from query parameters.
    # "credit" may contain legitimate HTML (links from the Commons API
    # Artist field) — sanitize with nh3, allowing only safe inline tags.
    data = {
        "credit": nh3.clean(
            request.args.get("credit", ""),
            tags={"a", "span", "bdi"},
            attributes={"a": {"href"}},
            link_rel=None,
        ),
        "descr": request.args.get("descr", ""),
        "file_url": request.args.get("file_url", ""),
        "file_title": request.args.get("file_title", ""),
        "license_title": request.args.get("license_title", ""),
        "license_url": request.args.get("license_url", ""),
        "upload_date": request.args.get("upload_date", ""),
        "usage": request.args.get("usage", ""),
    }

    # Build description / date fragments (escape interpolated values)
    descr_fragment = ""
    if data["descr"]:
        descr_fragment = banana.translate(lang, "credit-my-cc-of-object").replace(
            "$1", str(escape(data["descr"]))
        )

    date_fragment = ""
    if data["upload_date"]:
        date_fragment = banana.translate(lang, "credit-my-cc-since-date").replace(
            "$1", str(escape(data["upload_date"]))
        )

    # Build example attribution lines — Markup.format() auto-escapes
    # arguments unless they are already Markup objects.  credit is
    # wrapped in Markup() because it was already sanitized by nh3 above.
    example_online = Markup('<a href="{}">{}</a> / <span>{}</span> / <a href="{}">{}</a>').format(
        data["file_url"],
        data["file_title"],
        Markup(data["credit"]),
        data["license_url"],
        data["license_title"],
    )
    example_offline = (
        f"{escape(data['file_title'])} @ Wikimedia Commons / "
        f"{escape(_strip_html(data['credit']))} / "
        f"{escape(data['license_title'])}"
    )

    # Look up the letter template — either a standard tone or an "other" letter
    if tone in VALID_TONES:
        msg_key = f"credit-my-cc-letter-template-{tone}"
        letter_html = banana.translate(lang, msg_key)
        if letter_html is None:
            letter_html = banana.translate("en", msg_key) or ""
    else:
        # Check "other" letters for this language
        other = {lt["slug"]: lt for lt in OTHER_LETTERS.get(lang, [])}
        if tone not in other:
            return jsonify({"error": "invalid_tone"}), 400
        letter_html = other[tone]["html"]

    # Replace all $N placeholders with the actual values.
    # Plain-text values are escaped; credit is already sanitized by nh3.
    #
    # $1  = description fragment      $6  = license title
    # $2  = usage URL                 $7  = license URL
    # $3  = date fragment             $8  = file title
    # $4  = file URL (Commons)        $9  = example online
    # $5  = credit / attribution      $10 = example offline
    #
    # Replace $10 before $1 to avoid partial match.
    replacements = [
        ("$10", str(example_offline)),
        ("$1", descr_fragment),
        ("$2", str(escape(data["usage"]))),
        ("$3", date_fragment),
        ("$4", str(escape(data["file_url"]))),
        ("$5", data["credit"]),
        ("$6", str(escape(data["license_title"]))),
        ("$7", str(escape(data["license_url"]))),
        ("$8", str(escape(data["file_title"]))),
        ("$9", str(example_online)),
    ]
    for placeholder, value in replacements:
        letter_html = letter_html.replace(placeholder, value)

    return letter_html


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
