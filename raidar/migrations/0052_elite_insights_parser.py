from django.db import migrations, models

ELITE_CHOICES = [
    (-1, 'All'),
    (0, 'Core'),
    (1, 'Heart of Thorns'),
    (2, 'Path of Fire'),
    (3, 'End of Dragons'),
    (4, 'Visions of Eternity'),
]


class Migration(migrations.Migration):
    """Schema changes for encounters parsed by Elite Insights."""

    dependencies = [
        ('raidar', '0051_update_stat_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='encounterdata',
            name='parser_version',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='encounterdata',
            name='metrics',
            field=models.TextField(default='[]', editable=False),
        ),
        migrations.AddField(
            model_name='encounterphase',
            name='end_tick',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='participation',
            name='elite',
            field=models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True),
        ),
        migrations.AlterField(
            model_name='buildstat',
            name='elite',
            field=models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True),
        ),
        migrations.AlterField(
            model_name='userstat',
            name='elite',
            field=models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True),
        ),
    ]
