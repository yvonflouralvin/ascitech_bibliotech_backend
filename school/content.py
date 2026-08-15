"""Acces au contenu des livres stocke sur le systeme de fichiers.

Chaque livre possede un dossier `<BOOKS_CONTENT_ROOT>/<book_uuid>/` contenant une
page par fichier, sous la forme `content_01.txt`, `content_02.txt`, ...  Le fichier
contient l'image de la page encodee en base64.

Ce module centralise la resolution des chemins pour deux raisons :

1. la lecture d'une page ne doit jamais dependre du repertoire courant du process ;
2. la convention de nommage n'est pas garantie identique pour tous les imports
   (largeur du zero-padding, extension, index de depart).  Les livres importes
   depuis un EPUB, par exemple, n'ont pas forcement de `content_01.txt` : la
   resolution est donc tolerante et sait retrouver la premiere page disponible.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from django.conf import settings

# Extensions acceptees pour une page. `.txt`/`.b64` contiennent du base64 ;
# les extensions image sont lues en binaire puis encodees a la volee.
TEXT_SUFFIXES = {".txt", ".b64"}
BINARY_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PAGE_SUFFIXES = TEXT_SUFFIXES | BINARY_SUFFIXES

# `content_01.txt`, `content_1.txt`, `content_001.jpg`, `page_01.txt`, `01.txt`...
PAGE_FILE_RE = re.compile(
    r"^(?:content|page|p)?[-_]?(\d+)(?P<ext>\.[A-Za-z0-9]+)$",
    re.IGNORECASE,
)

# Signatures base64 des formats d'image usuels, pour renseigner le type MIME
# plutot que de supposer du JPEG cote client.
BASE64_MAGIC = (
    ("/9j/", "image/jpeg"),
    ("iVBORw0KGgo", "image/png"),
    ("R0lGOD", "image/gif"),
    ("UklGR", "image/webp"),
    ("PHN2Zw", "image/svg+xml"),
    ("PD94bWw", "image/svg+xml"),
)
DEFAULT_MIME = "image/jpeg"


def guess_mime(payload: str) -> str:
    """Deduit le type MIME d'une image a partir de son prefixe base64."""
    head = payload.lstrip()[:16]
    for prefix, mime in BASE64_MAGIC:
        if head.startswith(prefix):
            return mime
    return DEFAULT_MIME


def book_directory(book_id) -> Path | None:
    """Dossier de contenu d'un livre, ou None si l'identifiant n'est pas un UUID.

    Le passage par `UUID()` garantit qu'aucune valeur controlee par le client ne
    peut sortir de `BOOKS_CONTENT_ROOT` (pas de `..`, pas de separateur).
    """
    try:
        book_uuid = UUID(str(book_id))
    except (ValueError, AttributeError, TypeError):
        return None
    return Path(settings.BOOKS_CONTENT_ROOT) / str(book_uuid)


def _page_index(path: Path) -> int | None:
    match = PAGE_FILE_RE.match(path.name)
    if not match or path.suffix.lower() not in PAGE_SUFFIXES:
        return None
    return int(match.group(1))


def page_files(book_id) -> dict[int, Path]:
    """Table {numero de page -> fichier} pour un livre.

    Tolere les differentes largeurs de zero-padding et extensions.  En cas de
    doublon (`content_1.txt` et `content_01.txt`), le nom le plus court gagne
    pour rester deterministe.
    """
    directory = book_directory(book_id)
    if directory is None or not directory.is_dir():
        return {}

    found: dict[int, Path] = {}
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        index = _page_index(entry)
        if index is None:
            continue
        current = found.get(index)
        if current is None or (len(entry.name), entry.name) < (len(current.name), current.name):
            found[index] = entry
    return found


def resolve_page(book_id, order: int) -> Path | None:
    """Fichier correspondant a la page `order`, ou None s'il n'existe pas."""
    directory = book_directory(book_id)
    if directory is None:
        return None

    # Chemin direct (cas nominal, sans lister le dossier) : `content_01.txt`.
    for name in (f"content_{order:02}.txt", f"content_{order}.txt"):
        candidate = directory / name
        if candidate.is_file():
            return candidate

    return page_files(book_id).get(order)


#: Nombre de pages examinees au maximum pour trouver une couverture lisible.
COVER_SCAN_PAGES = 6

#: Proportion minimale de pixels non blancs pour qu'une page soit consideree
#: comme porteuse de contenu. Mesure sur le fonds reel : les pages blanches des
#: EPUB convertis plafonnent a 0,35 % tandis qu'une vraie couverture depasse 5 %.
MIN_INK_RATIO = 0.01

#: Seuil de luminance en dessous duquel un pixel compte comme "encre".
INK_LUMINANCE = 240


def ink_ratio(path: Path) -> float | None:
    """Proportion de pixels non blancs d'une page.

    Renvoie None si l'image n'est pas analysable (Pillow absent, fichier
    illisible) : l'appelant considere alors la page comme utilisable, ce qui
    preserve le comportement anterieur.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        import io

        with Image.open(io.BytesIO(_decode_source(path))) as image:
            # `draft` permet a la JPEG un decodage direct en basse resolution :
            # l'analyse ne coute alors qu'une fraction du decodage complet.
            image.draft("L", (64, 64))
            sample = image.convert("L").resize((64, 64))
            pixels = list(sample.getdata())
    except Exception:
        return None

    if not pixels:
        return None
    return sum(1 for value in pixels if value < INK_LUMINANCE) / len(pixels)


def _cover_cache_file(book_id) -> Path | None:
    directory = book_directory(book_id)
    if directory is None:
        return None
    return _thumbnail_root() / "covers" / f"{directory.name}.txt"


def resolve_cover(book_id) -> Path | None:
    """Fichier de couverture : la premiere page reellement lisible du livre.

    Deux ecueils sont couverts :

    1. la numerotation ne commence pas forcement a 1 ;
    2. la conversion d'un EPUB en images produit une ou deux pages de garde
       **blanches** avant le contenu. Elles existent sur le disque, mais les
       servir revient a afficher un rectangle vide. On les ignore donc au profit
       de la premiere page porteuse de contenu.

    Si aucune des premieres pages n'a de contenu, on renvoie None : le client
    dessine alors une couverture generee, plus informative qu'une page blanche.
    """
    pages = page_files(book_id)
    if not pages:
        return None

    ordered = sorted(pages)

    # Le choix est memorise : l'analyse ne se refait pas a chaque affichage.
    cache_file = _cover_cache_file(book_id)
    if cache_file is not None and cache_file.is_file():
        try:
            cached = int(cache_file.read_text(encoding="utf-8").strip())
            if cached in pages:
                return pages[cached]
            if cached == -1:
                return None
        except (OSError, ValueError):
            pass

    chosen: int | None = None
    for number in ordered[:COVER_SCAN_PAGES]:
        ratio = ink_ratio(pages[number])
        # ratio inconnu : on garde la page plutot que de risquer un faux rejet.
        if ratio is None or ratio >= MIN_INK_RATIO:
            chosen = number
            break

    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(str(chosen if chosen is not None else -1), encoding="utf-8")
        except OSError:
            pass

    return pages[chosen] if chosen is not None else None


def read_page_payload(path: Path) -> str:
    """Contenu base64 d'un fichier de page, quelle que soit son extension."""
    if path.suffix.lower() in BINARY_SUFFIXES:
        import base64

        return base64.b64encode(path.read_bytes()).decode("ascii")
    return path.read_text(encoding="utf-8")


def count_pages(book_id) -> int:
    """Nombre de pages reellement disponibles sur le disque pour un livre."""
    return len(page_files(book_id))


# --- Vignettes -------------------------------------------------------------
#
# Une page pleine resolution pese environ 1 Mo en base64. Afficher une grille de
# 70 couvertures a cette taille est inutilement couteux, en particulier sur une
# connexion mobile : on genere donc une version reduite, mise en cache sur disque.

THUMBNAIL_QUALITY = 78
MIN_THUMBNAIL_WIDTH = 80
MAX_THUMBNAIL_WIDTH = 1200


def _thumbnail_root() -> Path:
    return Path(
        getattr(
            settings,
            "BOOKS_THUMBNAIL_ROOT",
            Path(settings.BOOKS_CONTENT_ROOT).parent / ".thumbnails",
        )
    )


def _decode_source(path: Path) -> bytes:
    """Octets bruts de l'image, que le fichier soit du base64 ou du binaire."""
    import base64

    if path.suffix.lower() in BINARY_SUFFIXES:
        return path.read_bytes()
    return base64.b64decode(path.read_text(encoding="utf-8"), validate=False)


def build_thumbnail(path: Path, width: int) -> tuple[str, str] | None:
    """Vignette JPEG encodee en base64, ou None si la reduction est impossible.

    Retourner None n'est pas une erreur : l'appelant sert alors l'image
    d'origine. C'est le cas si Pillow n'est pas installe ou si le fichier
    source n'est pas une image exploitable.
    """
    import base64

    width = max(MIN_THUMBNAIL_WIDTH, min(int(width), MAX_THUMBNAIL_WIDTH))

    try:
        from PIL import Image
    except ImportError:
        return None

    cache_dir = _thumbnail_root()
    try:
        stamp = int(path.stat().st_mtime)
    except OSError:
        return None

    cache_file = cache_dir / f"{path.parent.name}_{path.stem}_{width}_{stamp}.jpg"

    if cache_file.is_file():
        try:
            return base64.b64encode(cache_file.read_bytes()).decode("ascii"), "image/jpeg"
        except OSError:
            pass

    try:
        import io

        with Image.open(io.BytesIO(_decode_source(path))) as image:
            image = image.convert("RGB")
            # La hauteur est laissee libre : `thumbnail` conserve le ratio.
            image.thumbnail((width, width * 4), Image.LANCZOS)

            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
            payload = buffer.getvalue()
    except Exception:
        # Image illisible, tronquee ou format non supporte : on laisse
        # l'appelant servir l'original.
        return None

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(payload)
    except OSError:
        # Cache non inscriptible (volume en lecture seule) : sans consequence,
        # la vignette est simplement regeneree a chaque appel.
        pass

    return base64.b64encode(payload).decode("ascii"), "image/jpeg"
