from django.db import migrations, models

from analyser.bosses import MODE_SUFFIXES, Mode, area_name_and_mode


def split_names(apps, schema_editor):
    """Moves the mode out of the area names ("Cairn (CM)") into the new flags."""
    Area = apps.get_model('raidar', 'Area')
    for area in Area.objects.all():
        name, mode = area_name_and_mode(area.id, area.name)
        area.name = name
        area.is_cm = mode == Mode.CM
        area.is_lcm = mode == Mode.LEGENDARY_CM
        area.save()


def join_names(apps, schema_editor):
    Area = apps.get_model('raidar', 'Area')
    for area in Area.objects.all():
        mode = Mode.LEGENDARY_CM if area.is_lcm else Mode.CM if area.is_cm else Mode.NORMAL
        area.name += MODE_SUFFIXES.get(mode, "")
        area.save()


class Migration(migrations.Migration):
    """Areas of the same boss share its name; challenge modes are told apart by flags instead of by name."""

    dependencies = [
        ('raidar', '0054_encounter_phase_parent'),
    ]

    operations = [
        migrations.AddField(
            model_name='area',
            name='is_cm',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='area',
            name='is_lcm',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='area',
            name='name',
            field=models.CharField(max_length=64),
        ),
        migrations.RunPython(split_names, join_names),
    ]
