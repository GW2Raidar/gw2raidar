# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-10-06 00:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('raidar', '0024_blank_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='era',
            name='value',
            field=models.TextField(default='{}'),
        ),
    ]
