from django.db import migrations, models


class Migration(migrations.Migration):
    """Buffs are no longer a fixed list: each encounter stores the buffs the parser found in it."""

    dependencies = [
        ('raidar', '0052_elite_insights_parser'),
    ]

    operations = [
        migrations.AddField(
            model_name='encounterdata',
            name='buffs',
            field=models.TextField(default='[]', editable=False),
        ),
    ]
