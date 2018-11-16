import os, sys, django, base64, json
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gw2raidar.settings")
django.setup()

from raidar.models import *

era = Era.objects.latest('started_at')
for store in era.era_area_stores.iterator():
    cutoffs = {}

    try:
        builds = store.val['All']['build']
    except KeyError:
        continue
    
    for prof_id, prof_data in builds.items():
        if prof_id == 'All': continue
        for elite_id, elite_data in prof_data.items():
            if elite_id == 'All': continue
            for arch_id, arch_data in elite_data.items():
                if arch_id == 'All': continue
                per_dps_str = arch_data['per_dps']
                per_dps = list(np.frombuffer(base64.b64decode(per_dps_str.encode('utf-8')), dtype=np.float32).astype(float))
                cutoffs[(int(prof_id), int(elite_id), int(arch_id))] = per_dps[95]

    encounters = Encounter.objects.filter(
        era=era, area_id=store.area_id)
    for encounter in encounters.iterator():
        val = encounter.val
        for participation in encounter.participations.all():
            cleave_stats = val['Category']['combat']['Phase']['All']['Player'][participation.character]['Metrics']['damage']['To']['*All']
            dps = cleave_stats['dps']
            if dps >= cutoffs[(participation.profession, participation.elite, participation.archetype)]:
                skills = cleave_stats['Skill']
                line = {
                    'area_id': encounter.area_id,
                    'url_id': encounter.url_id,
                    'started_at': encounter.started_at,
                    'prof': int(participation.profession),
                    'elite': int(participation.elite),
                    'arch': int(participation.archetype),
                    'skills': skills
                }
                print(json.dumps(line))
