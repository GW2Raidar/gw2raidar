from django.db import migrations


class Migration(migrations.Migration):
    """Second half of 0055, apart from it so the names are changed before the new constraint is made."""

    dependencies = [
        ('raidar', '0055_area_modes'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='area',
            unique_together={('name', 'is_cm', 'is_lcm')},
        ),
        migrations.AlterModelOptions(
            name='area',
            options={'ordering': ('name', 'is_lcm', 'is_cm')},
        ),
    ]
