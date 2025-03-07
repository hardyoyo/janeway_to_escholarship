from django.core.management.base import BaseCommand

import json, csv

from utils.models import LogEntry
from journal.models import Journal
from django.contrib.contenttypes.models import ContentType

from plugins.eschol.models import EscholArticle
from identifiers.models import Identifier

# The following query to the jschol db will create the expected input file
# "SELECT arks.id, arks.source, external_id, items.attrs->>'$.doi' as doi FROM arks LEFT JOIN unit_items ON arks.id = unit_items.item_id LEFT JOIN items ON items.id = arks.id  WHERE unit_id = '<journal-code>';"

class Command(BaseCommand):
    """Adds EscholArticle objects with arks for items imported from OJS for a given journal"""
    help = "Adds EscholArticle objects for items imported from OJS for a given journal"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to add arks", type=str
        )
        parser.add_argument(
            "import_file", help="path to an export file containing the ojs ids and arks", type=str
        )

    def handle(self, *args, **options):
        journal_code = options.get("journal_code")
        import_file = options.get("import_file")

        j = Journal.objects.get(code=journal_code)

        id_map = {}
        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter="\t")
            for r in reader:
                id_map[r["external_id"]] = {"ark": r["id"], "source": r["source"], "doi": r["doi"]}

        ctype = ContentType.objects.get(app_label='submission', model='article')

        for a in j.article_set.all():
            desc = f'Article {a.pk} imported by Journal Transporter.'
            e = LogEntry.objects.filter(content_type=ctype, object_id=a.pk, description__startswith=desc)
            if e.count() > 1:
                print(f'ERROR Article {a.pk}: multiple log entries found')
            elif e.count() < 1:
                print(f'ERROR Article {a.pk}: no log entries found')
            else:
                d = json.loads(e[0].description.partition("Import metadata:")[2])

                for i in d['external_identifiers']:
                    if i['name'] == "source_id":
                        ojs_id = i['value']

                if ojs_id in id_map:
                    ark = f'ark:/13030/{id_map[ojs_id]["ark"]}'
                    source = id_map[ojs_id]["source"]

                    e, created = EscholArticle.objects.get_or_create(article=a, ark=ark, source_name=source)
                    if created:
                        print(f'Created eschol article {ark}')
                    else:
                        print(f'Got eschol article {ark}')

                    if "doi" in id_map[ojs_id] and not id_map[ojs_id]["doi"] == 'NULL':
                        doi_options = {
                            'id_type': 'doi',
                            'identifier': id_map[ojs_id]["doi"],
                            'article': a
                        }

                        doi = Identifier.objects.create(**doi_options)
                        e.is_doi_registered = True
                        e.save()
                        print(f'Added doi {doi}')
                else:
                    if a.stage == 'Published':
                        print(f'ERROR Published article {a.pk}: OJS id not found in export')
