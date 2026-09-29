"""Cree les neuf domaines thematiques proposes pour le classement du fonds.

Les categories sont des donnees, pas des constantes de code : elles restent
modifiables dans l'administration. Cette migration se contente de poser le
socle initial, sans ecraser une categorie deja presente portant le meme slug.
"""

from django.db import migrations

CATEGORIES = [
    (10, "sciences-et-mathematiques", "Sciences et Mathématiques"),
    (20, "informatique-technologie-et-robotique", "Informatique, Technologie et Robotique"),
    (30, "langues-et-litterature", "Langues et Littérature"),
    (40, "sciences-humaines-et-sociales", "Sciences humaines et sociales"),
    (50, "economie-gestion-et-entrepreneuriat", "Économie, Gestion et Entrepreneuriat"),
    (60, "arts-et-culture", "Arts et Culture"),
    (70, "developpement-personnel-et-orientation", "Développement personnel et Orientation"),
    (80, "religion-et-spiritualite", "Religion et Spiritualité"),
    (90, "encyclopedies-et-ouvrages-de-reference", "Encyclopédies et Ouvrages de référence"),
]


def create_categories(apps, schema_editor):
    Category = apps.get_model("school", "Category")
    for order, slug, name in CATEGORIES:
        Category.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "order": order},
        )


def delete_categories(apps, schema_editor):
    """Retire uniquement les categories du socle encore inutilisees.

    Une categorie a laquelle des livres ont ete rattaches est conservee : la
    marche arriere d'une migration ne doit pas detruire un classement saisi
    par l'administration.
    """
    Category = apps.get_model("school", "Category")
    for _, slug, _ in CATEGORIES:
        Category.objects.filter(slug=slug, books__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("school", "0012_category"),
    ]

    operations = [
        migrations.RunPython(create_categories, delete_categories),
    ]
