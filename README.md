GW2 Raidar
==========

Quickstart
----------

* Install Python 3 and pip3
* `pip install django pandas requests django-taggit psycopg2 django-cors-headers djangorestframework django-rest-swagger`
* Optionally for development, `pip3 install django-debug-toolbar django-debug-toolbar-request-history`
* `python3 manage.py migrate`
* `python3 manage.py createsuperuser`
* `python3 manage.py runserver`
* Browse to http://localhost:8000/

To generate statistics, use `python3 manage.py restat [-f] [-v{0,1,2,3}]`.

To process new uploads, use `python3 manage.py process_uploads [-v{0,1,2,3}]`.


<tr class="uk-margin-remove" >
                    <td>
                      <img class="uk-margin-remove" alt="[[data.specialisations[professionId][eliteId]]]" src="{% static 'raidar/img/20px/' %}/[[data.specialisations[professionId][eliteId]]]_tango_icon_20px.png" />
                      [[professionId === 'All' ? 'All' : data.specialisations[professionId][eliteId]]]
                    </td>
                    [[#each [
                      {"percentiles": p(lineStats.per_dps), "max": individual.max_dps},
                      {"percentiles": boss_dps_percentiles, "max": individual.max_dps_boss},
                      buffs[0],
                      buffs[1],
                      buffs[2] ,
                      buffs[3],
                      buffs[4]
                    ] ]]
                      [[#if percentiles]]
                      <td class="uk-margin-remove" uk-tooltip title="99th percentile: [[num(percentiles[99], 0)]]<br/>90th percentile: [[num(percentiles[90], 0)]]<br/>median: [[num(percentiles[50], 0)]]" style="[[p_bar(percentiles, max, buff_image)]];min-width:[[buff_image ? 80 : 145]]px">
                        [[#if buff_image]]
                          <img class="uk-float-left" src="{% static 'raidar/img/buff/' %}/[[buff_image]].png" alt="[[buff_name]]"/>
                        [[/if]]
                      </td>
                      [[else]]
                      <td></td>
                      [[/if]]
                    [[/each]]
                    <td>[[num(lineStats.count/group.count, 2)]]</td>
                  </tr>