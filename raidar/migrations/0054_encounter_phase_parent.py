from django.db import migrations, models


class Migration(migrations.Migration):
    """Phases can be nested: a phase now names the phase it is a part of."""

    dependencies = [
        ('raidar', '0053_encounter_buffs'),
    ]

    operations = [
        migrations.AddField(
            model_name='encounterphase',
            name='parent',
            field=models.TextField(blank=True, null=True),
        ),
    ]
