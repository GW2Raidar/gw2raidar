# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-11-08 01:28
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('raidar', '0031_regular_blank_null'),
    ]

    operations = [
        migrations.AlterField(
            model_name='encounter',
            name='has_evtc',
            field=models.BooleanField(default=True, editable=False),
        ),
    ]