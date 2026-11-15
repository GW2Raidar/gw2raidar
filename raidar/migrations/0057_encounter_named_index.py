from django.db import migrations, models

INDEX_NAME = 'raidar_enc_area_started_idx'


def name_index(apps, schema_editor):
    """Names the (area, started_at) index of the encounters, or creates it where it is missing.

    Databases set up before Django 5.1 have this index under a generated name, from index_together
    in 0001_initial. Newer Django versions ignore index_together when they replay that migration,
    so databases created since do not have the index at all.
    """
    Encounter = apps.get_model('raidar', 'Encounter')
    table = Encounter._meta.db_table
    columns = [Encounter._meta.get_field(name).column for name in ('area', 'started_at')]
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, table)
    existing = [name for name, constraint in constraints.items()
                if constraint['index'] and not constraint['unique'] and constraint['columns'] == columns]

    index = models.Index(fields=['area', 'started_at'], name=INDEX_NAME)
    if INDEX_NAME in existing:
        return
    if existing:
        old_index = models.Index(fields=['area', 'started_at'], name=existing[0])
        schema_editor.rename_index(Encounter, old_index, index)
    else:
        schema_editor.add_index(Encounter, index)


class Migration(migrations.Migration):
    """Meta.index_together is gone from Django; the same index is now declared (and named) in Meta.indexes."""

    dependencies = [
        ('raidar', '0056_area_unique_mode'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameIndex(
                    model_name='encounter',
                    new_name=INDEX_NAME,
                    old_fields=('area', 'started_at'),
                ),
            ],
            database_operations=[
                migrations.RunPython(name_index, migrations.RunPython.noop),
            ],
        ),
    ]
