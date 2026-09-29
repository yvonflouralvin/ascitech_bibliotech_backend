"""Pre-classement du fonds existant dans les domaines thematiques.

La commande ne decide rien seule : par defaut elle se contente d'imprimer ce
qu'elle ferait. C'est une aide a la reprise des livres deja en base, pas un
classificateur fiable — un titre ne dit pas toujours de quoi parle un
ouvrage. Les propositions se relisent, puis s'appliquent avec `--apply`, et
tout ce qui reste ambigu est laisse sans categorie pour un arbitrage humain.

    python manage.py classify_books              # simulation
    python manage.py classify_books --apply      # ecriture
    python manage.py classify_books --apply --force   # reclasse aussi les livres deja classes
"""

import re
import unicodedata

from django.core.management.base import BaseCommand

from school.models import Book, Category

# Poids des champs : un mot-cle dans le titre est un signal bien plus sur que
# le meme mot perdu dans une description.
WEIGHT_TITLE = 3
WEIGHT_AUTHOR = 1
WEIGHT_DESCRIPTION = 1

# Score minimal pour proposer une categorie : l'equivalent d'un mot-cle dans
# le titre, ou de trois occurrences dans la description.
MIN_SCORE = 3

# Au-dela, la proposition devient du bruit plutot qu'un classement.
MAX_CATEGORIES = 3

# Nombre de titres partageant une meme tete pour la considerer comme un nom de
# collection. « STEAM SCIENCE. » ouvre quarante titres du fonds : compte comme
# un mot-cle, il rangerait « Learn to Draw » dans les sciences. Un nom de
# collection decrit l'editeur, pas le sujet du livre.
COLLECTION_MIN_BOOKS = 5

# Mots-cles par slug de categorie, sans accents (le texte compare l'est aussi).
# Le fonds est bilingue — la collection STEAM est en anglais — d'ou les termes
# des deux langues dans chaque liste.
# Une expression contenant une espace est cherchee telle quelle ; un mot seul
# est cherche entre frontieres de mot, pour que « art » n'attrape pas
# « partage ».
KEYWORDS = {
    "sciences-et-mathematiques": [
        "mathematique", "mathematiques", "maths", "algebre", "geometrie", "arithmetique",
        "trigonometrie", "logarithme", "equation", "equations", "integrale", "derivee",
        "vecteur", "matrice", "calcul", "statistique", "statistiques", "probabilite",
        "probabilites", "physique", "chimie", "chimique", "biologie", "svt", "science",
        "sciences", "scientifique", "botanique", "zoologie", "anatomie", "astronomie",
        "geologie", "thermodynamique", "optique", "atome", "molecule", "cellule",
        "genetique", "ecologie",
        # Anglais (collection STEAM)
        "mathematics", "math", "arithmetic", "geometry", "fractions", "numbers",
        "shapes", "measure", "telling time", "physical sciences", "life sciences",
        "biology", "chemistry", "physics", "body", "universe", "earth", "natural",
        "agricultural",
    ],
    "informatique-technologie-et-robotique": [
        "informatique", "ordinateur", "programmation", "programmer", "algorithme",
        "algorithmique", "python", "java", "javascript", "html", "css", "php", "sql",
        "base de donnees", "bases de donnees", "reseau", "reseaux", "logiciel",
        "internet", "web", "intelligence artificielle", "robotique", "robot", "arduino",
        "raspberry", "electronique", "electricite", "technologie", "technologique",
        "bureautique", "excel", "linux", "windows", "cybersecurite", "codage",
        "developpement web", "systeme d'exploitation", "machine", "machines",
        "electrique", "electriques", "mecanique", "ingenierie",
        # Anglais (collection STEAM)
        "computer", "technology", "coding", "robots", "engineering", "mechanical",
        "electrical", "electronical", "aerospace", "mobile phone", "inventions",
        "invention",
    ],
    "langues-et-litterature": [
        "francais", "anglais", "english", "grammaire", "conjugaison", "orthographe",
        "vocabulaire", "dictee", "litterature", "litteraire", "roman", "poesie", "poeme",
        "poemes", "theatre", "conte", "contes", "fable", "fables", "recit", "nouvelles",
        "redaction", "dissertation", "expression ecrite", "espagnol", "allemand",
        "latin", "grec", "lingala", "swahili", "kiswahili", "kikongo", "tshiluba",
        "langue", "langues", "langue francaise", "francaise", "lecture", "lire",
        "mots", "mot", "linguistique", "traduction", "syntaxe",
        # Anglais
        "english", "grammar", "reading", "spelling", "writing", "story", "stories",
        "tales", "vocabulary",
    ],
    "sciences-humaines-et-sociales": [
        "histoire", "historique", "geographie", "civisme", "education civique",
        "sociologie", "anthropologie", "psychologie", "philosophie", "philosophique",
        "politique", "droit", "juridique", "constitution", "citoyennete", "societe",
        "sociale", "demographie", "geopolitique", "colonisation", "independance",
        "civilisation", "ethique", "morale",
    ],
    "economie-gestion-et-entrepreneuriat": [
        "economie", "economique", "economiques", "gestion", "comptabilite", "comptable",
        "finance", "financier", "financiere", "marketing", "commerce", "commercial",
        "entreprise", "entreprises", "entrepreneuriat", "entrepreneur", "management",
        "banque", "bancaire", "investissement", "business", "fiscalite", "budget",
        "microeconomie", "macroeconomie", "cooperative", "negociation", "negocier",
        "marge", "marges", "vente", "ventes", "client", "clients",
    ],
    "arts-et-culture": [
        "art", "arts", "artistique", "musique", "musical", "chant", "chanson", "dessin",
        "peinture", "sculpture", "cinema", "photographie", "danse", "culture",
        "culturel", "culturelle", "esthetique", "architecture", "musee", "folklore",
        "patrimoine", "artisanat", "calligraphie", "couleur", "couleurs",
        # Anglais
        "colour", "colours", "color", "colors", "draw", "drawing", "painting",
        "music", "aesthetic",
    ],
    "developpement-personnel-et-orientation": [
        "developpement personnel", "motivation", "leadership", "confiance en soi",
        "estime de soi", "reussite", "reussir", "succes", "habitudes", "orientation",
        "metier", "metiers", "carriere", "emploi", "coaching", "bien-etre",
        "productivite", "gestion du temps", "discipline personnelle", "epanouissement",
        # Anglais
        "leader", "habits", "mindset", "self-help",
    ],
    "religion-et-spiritualite": [
        "bible", "biblique", "evangile", "jesus", "christ", "chretien", "chretienne",
        "religion", "religieux", "religieuse", "priere", "prieres", "spiritualite",
        "spirituel", "spirituelle", "dieu", "foi", "eglise", "coran", "islam",
        "musulman", "theologie", "catechese", "psaume", "psaumes", "apotre", "sainte",
    ],
    "encyclopedies-et-ouvrages-de-reference": [
        "encyclopedie", "encyclopedique", "dictionnaire", "lexique", "glossaire",
        "atlas", "almanach", "repertoire", "larousse", "memento", "precis de",
        "ouvrage de reference", "annuaire",
    ],
}


def normalize(text):
    """Minuscules sans accents : le texte source est saisi de facon inegale."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def count_matches(haystack, keyword):
    """Occurrences d'un mot-cle. Un mot seul respecte les frontieres de mot."""
    if " " in keyword or "-" in keyword or "'" in keyword:
        return haystack.count(keyword)
    return len(re.findall(rf"\b{re.escape(keyword)}\b", haystack))


def detect_collections(titles):
    """Tetes de titre communes a assez d'ouvrages pour etre des collections.

    Rien n'est code en dur : la detection se fait sur le fonds reellement
    present. Un titre isole garde donc toute sa tete, et une collection dont
    le nom porte quand meme un sujet ne fait au pire perdre qu'un signal —
    le livre ressort « indecis » et revient a l'arbitrage humain, ce qui vaut
    mieux qu'un classement faux.
    """
    counter = {}
    for title in titles:
        head = re.split(r"[.,:;]", normalize(title), maxsplit=1)[0].strip()
        # Une tete d'un seul mot est trop souvent le sujet lui-meme.
        if len(head.split()) < 2 or len(head) < 6:
            continue
        counter[head] = counter.get(head, 0) + 1
    return {head for head, count in counter.items() if count >= COLLECTION_MIN_BOOKS}


def strip_collection(title, collections):
    """Retire le nom de collection en tete de titre, s'il y en a un."""
    normalized = normalize(title)
    for head in collections:
        if normalized.startswith(head):
            return normalized[len(head):].lstrip(" .,:;-")
    return normalized


def score_book(book, collections=frozenset()):
    """Score par slug de categorie pour un livre donne."""
    fields = (
        (strip_collection(book.title, collections), WEIGHT_TITLE),
        (normalize(book.author), WEIGHT_AUTHOR),
        (normalize(book.description), WEIGHT_DESCRIPTION),
    )

    scores = {}
    for slug, keywords in KEYWORDS.items():
        total = 0
        for haystack, weight in fields:
            if not haystack:
                continue
            for keyword in keywords:
                total += count_matches(haystack, keyword) * weight
        if total:
            scores[slug] = total
    return scores


def propose(book, collections=frozenset()):
    """Slugs proposes pour un livre, du plus au moins probable."""
    scores = score_book(book, collections)
    retained = [(slug, score) for slug, score in scores.items() if score >= MIN_SCORE]
    retained.sort(key=lambda item: (-item[1], item[0]))
    return retained[:MAX_CATEGORIES]


class Command(BaseCommand):
    help = "Propose un classement thematique des livres a partir de leurs metadonnees."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Enregistre les propositions. Sans cette option, rien n'est ecrit.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Traite aussi les livres deja classes (leurs categories sont remplacees).",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        force = options["force"]

        categories = {c.slug: c for c in Category.objects.all()}
        missing = set(KEYWORDS) - set(categories)
        if missing:
            self.stderr.write(
                self.style.ERROR(
                    "Categories absentes de la base : "
                    + ", ".join(sorted(missing))
                    + ". Appliquer les migrations avant de relancer."
                )
            )
            return

        books = list(Book.objects.prefetch_related("categories").order_by("title"))

        collections = detect_collections(book.title for book in books)
        if collections:
            self.stdout.write(
                "Collections detectees (ignorees dans le score) : "
                + ", ".join(sorted(collections))
            )
            self.stdout.write("")

        classified = skipped = undecided = 0

        for book in books:
            existing = list(book.categories.all())
            if existing and not force:
                skipped += 1
                continue

            proposals = propose(book, collections)
            if not proposals:
                undecided += 1
                self.stdout.write(
                    f"  ? {book.title[:70]:<70} " + self.style.WARNING("indecis")
                )
                continue

            labels = ", ".join(
                f"{categories[slug].name} ({score})" for slug, score in proposals
            )
            self.stdout.write(f"  + {book.title[:70]:<70} {labels}")

            if apply_changes:
                book.categories.set([categories[slug] for slug, _ in proposals])
            classified += 1

        self.stdout.write("")
        summary = (
            f"{classified} livre(s) classe(s), {undecided} indecis, "
            f"{skipped} deja classe(s) et ignore(s)."
        )
        self.stdout.write(self.style.SUCCESS(summary))

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Simulation : aucune modification enregistree. "
                    "Relancer avec --apply pour appliquer."
                )
            )
