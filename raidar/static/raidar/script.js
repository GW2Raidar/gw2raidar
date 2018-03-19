"use strict";

// Acquire Django CSRF token for AJAX, and prefix the base URL
(function setupAjaxForAuth() {
  const PAGE_SIZE = 10;
  const PAGINATION_WINDOW = 5;

  const DEBUG = raidar_data.debug;
  Ractive.DEBUG = DEBUG;


  const inputDateAvailable = (() => {
    const smiley = '1)';
    const type = 'date';
    let input = document.createElement('input');
    input.setAttribute('type', type);
    input.value = smiley;
    return input.type === type && 'style' in input && input.value !== smiley;
  })();


  Ractive.decorators.ukUpdate = function(node) {
    UIkit.update();
    return {
      teardown: () => {
      },
    };
  };

  // bring tagsInput into Ractive
  Ractive.decorators.tagsInput = function(node, tagsPath) {
    let ractive = this;
    tagsPath = ractive.getContext(node).resolve(tagsPath);
    let classList = Array.from(node.classList);
    tagsInput(node);
    node.nextSibling.setValue(ractive.get(tagsPath));
    node.nextSibling.classList.add(...classList);
    if (node.getAttribute('readonly')) {
      node.nextSibling.firstChild.setAttribute('readonly', true);
    }
    node.addEventListener('change', function(evt) {
      let tags = node.nextSibling.getValue();
      if (r.get(tagsPath) != tags) {
        ractive.set(tagsPath, node.nextSibling.getValue());
      }
    });
    let observer = this.observe(tagsPath, (newValue, oldValue, keypath) => {
      if (node.nextSibling && newValue != oldValue) {
        node.nextSibling.setValue(newValue);
      }
    });
    return {
      teardown: () => {
        observer.cancel();
        node.nextSibling.remove();
      },
    };
  };


  let csrftoken = $('[name="csrfmiddlewaretoken"]').val();

  function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
  }
  $.ajaxSetup({
    beforeSend: function beforeSend(xhr, settings) {
      if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
        xhr.setRequestHeader("X-CSRFToken", csrftoken);
      }
      settings.url = baseURL + settings.url
    }
  });
  $(document).ajaxError((evt, xhr, settings, err) => {
    console.error(err);
    error("Error communicating to server");
  })

  function f0X(x) {
    return (x < 10) ? "0" + x : x;
  }

  let helpers = Ractive.defaults.data;
  let allRE = /^All(?: \w+ bosses)?$/;
  helpers.keysWithAllLast = (obj, lookup) => {
    let keys = Object.keys(obj);
    keys.sort((a, b) => {
      let aAll = a.match(allRE);
      let bAll = b.match(allRE);
      if (aAll && !bAll) return 1;
      if (!aAll && bAll) return -1;
      if (lookup && !(aAll && bAll)) {
        a = lookup[a];
        b = lookup[b];
      }
      if (a < b) return -1;
      if (a > b) return 1;
      return 0;
    });
    return keys;
  };
  helpers.flattenStats = (build) => {
    let all = [];
    Object.keys(build || {}).forEach((professionId) => {
      Object.keys(build[professionId] || {}).forEach((eliteId) => {
        Object.keys(build[professionId][eliteId] || {}).forEach((archetypeId) => {
          if('count' in build[professionId][eliteId][archetypeId])
            all.push({
              'professionId':professionId,
              'eliteId': eliteId,
              'archetypeId': archetypeId,
              'boss_dps_percentiles': helpers.p(build[professionId][eliteId][archetypeId].per_dps_boss)
            });
        });
      });
    });
    all.sort((a,b) => b.boss_dps_percentiles[99] - a.boss_dps_percentiles[99])
    return all
  }
  helpers.findId = (list, id) => {
    return list.find(a => a.id == id);
  }
  helpers.round = (n, d=0) => {
    return n.toFixed(d);
  }
  // adapted from https://stackoverflow.com/a/2901298/240443
  // in accordance to https://en.wikipedia.org/wiki/Wikipedia:Manual_of_Style/Dates_and_numbers#Decimal_points
  // num(1234.5):     1,234.5
  // num(1234.5, 2):  1,234.50
  // num(1234.5, 0):  1,234
  // num(0.1234567):  0.123,4567
  // num(0.12345678): 0.123,456,78
  let digitGrouper = ',';
  let decimalSeparator = '.';
  helpers.num = (n, d) => {
    if (n === undefined) return '';
    let s = d == null ? n.toString() : n.toFixed(d);
    let p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, digitGrouper);
    if (p[1] && digitGrouper == ' ') p[1] = p[1].replace(/(\d{3})(?!\d$)\B/g, '$1' + digitGrouper);
    return p.join(decimalSeparator);
  }
  // special for percentages, defaults to 2 decimal digits (`null` is natural formatting)
  // perc(23.2):     23.20%
  // perc(23.2, 0):  23%
  // perc(23.2):     23.2%
  helpers.perc = (n, d) => {
    if (n === undefined) return '';
    return helpers.num(n, d === undefined ? 2 : d) + '%';
  }
  // e.g. pctl(per_might)
  helpers.pctl = base64 => {
    if (!base64) return [];
    return new Float32Array(Uint8Array.from(atob(base64), c => c.charCodeAt(0)).buffer);
  }
  // e.g. bsearch(might, pctl(per_might))
  helpers.bsearch = (needle, haystack) => {
    if (!haystack.length) return 0;
    let l = 0, h = haystack.length - 1;
    if (needle > haystack[h]) {
      return h + 1;
    }
    while (l != h) {
      let m = (l + h) >> 1;
      if (haystack[m] < needle) {
        l = m + 1;
      } else {
        h = m;
      }
    }
    return h;
  };
  helpers.th = num => {
    let ones = num % 10;
    let tens = num % 100 - ones;
    let suffix = tens == 1 ? "th" : ones == 1 ? "st" : ones == 2 ? "nd" : ones == 3 ? "rd" : "th";
    return num + suffix;
  };
  helpers.buffImportanceLookup = {
    'might': 80,
    'fury': 10,
    'quickness': 25,
    'alacrity': 15,
    'protection': 15,
    'retaliation': 5,
    'aegis': 25,
    'resist': 15,
    'stab': 8,
    'vigor': 15,
    'spotter': 5,
    'glyph_of_empowerment': 10,
    'spirit_of_frost': 7.5,
    'sun_spirit': 6,
    'empower_allies': 5,
    'banner_strength': 8,
    'banner_discipline': 8,
    'assassins_presence': 6,
    'naturalistic_resonance': 20,
    'pinpoint_distribution': 5,
    'soothing_mist': 10,
    'vampiric_presence': 5,
  }
  helpers.buffStackLookup = {
    'might': 25,
    'stab': 25,
  }
  helpers.buffImageLookup = {
    'might': 'Might',
    'fury': 'Fury',
    'quickness': 'Quickness',
    'alacrity': 'Alacrity',
    'protection': 'Protection',
    'retaliation': 'Retaliation',
    'regen': 'Regeneration',
    'aegis': 'Aegis',
    'resist': 'Resistance',
    'stab': 'Stability',
    'swift': 'Swiftness',
    'vigor': 'Vigor',
    'spotter': 'Spotter',
    'glyph_of_empowerment': 'Glyph_of_Empowerment',
    'spirit_of_frost': 'Frost_Spirit',
    'sun_spirit': 'Sun_Spirit',
    'stone_spirit': 'Stone_Spirit',
    'storm_spirit': 'Storm_Spirit',
    'empower_allies': 'Empower_Allies',
    'banner_strength': 'Banner_of_Strength',
    'banner_discipline': 'Banner_of_Discipline',
    'banner_tactics': 'Banner_of_Tactics',
    'banner_defence': 'Banner_of_Defense',
    'assassins_presence': 'Assassin\'s_Presence',
    'naturalistic_resonance': 'Facet_of_Nature',
    'pinpoint_distribution': 'Pinpoint_Distribution',
    'soothing_mist': 'Soothing_Mist',
    'vampiric_presence': 'Vampiric_Presence',
  }
  helpers.buffImportance = (buff) => {
    if(buff in helpers.buffImportanceLookup) {
      return helpers.buffImportanceLookup[buff];
    }
    return 1;
  }
  helpers.buffMax = (buff) => {
    if(buff in helpers.buffStackLookup) {
      return helpers.buffStackLookup[buff];
    }
    return 100;
  }
  helpers.highestBuffs = (buffs) => {
    let buffNames = [];
    Object.keys(buffs).forEach((buff) => {
        if(buff.startsWith("max_"))
        buffNames.push(buff.substring(4))
    });

    let buffInfo = buffNames.map((buff) => { return {
        "percentiles": helpers.p(buffs["per_" + buff]),
        "max": helpers.buffMax(buff) * 10,
        "buff_name": buff,
        "buff_image": helpers.buffImageLookup[buff] || buff,
        "importance": helpers.buffImportance(buff) * buffs["avg_" + buff]
    }}).filter((a) => a.importance >= 500);

    buffInfo.sort((a,b) => b.importance - a.importance);
    return buffInfo;
  }
  helpers.formatDate = timestamp => {
    if (timestamp !== undefined) {
      let date = new Date(timestamp * 1000);
      return `${date.getFullYear()}-${f0X(date.getMonth() + 1)}-${f0X(date.getDate())} ${f0X(date.getHours())}:${f0X(date.getMinutes())}:${f0X(date.getSeconds())}`;
    } else {
      return '';
    }
  };
  helpers.formatTime = duration => {
    if (duration !== undefined) {
      let seconds = Math.trunc(duration);
      let minutes = Math.trunc(seconds / 60);
      let usec = Math.trunc((duration - seconds) * 1000);
      seconds -= minutes * 60
      if (usec < 10) usec = "00" + usec;
      else if (usec < 100) usec = "0" + usec;
      if (minutes) return minutes + ":" + f0X(seconds) + "." + usec;
      return seconds + "." + usec;
    } else {
      return '';
    }
  };
  helpers.tagForMechanic = (context, metricData) => {
    let metrics, ok, actualPhase;
    try {
      actualPhase = r.get('page.phase');
      let phase = metricData.split_by_phase ? actualPhase : 'All';
      metrics = context.phases[phase].mechanics;
      ok = metrics && metricData.name in metrics;
    } catch (e) {
      ok = false;
    }
    if (!ok) return "<td/>";

    let ignore = (actualPhase == 'All' || metricData.split_by_phase) ? '' : 'class="ignore"';
    let value = metrics[metricData.name];
    switch (metricData.data_type) {
      case 0: // time
        value = "[" + helpers.formatTime(value / 1000) + "]";
        break;
      case 1: // count
        value = helpers.num(value);
        break;
    }
    return `<td ${ignore}>${value}</td>`;
  }
  class Colour {
    constructor(r, g, b, a) {
      if (typeof(r) == 'string') {
        [this.r, this.g, this.b] = r.match(Colour.colRE).slice(1).map(x => parseInt(x, 16));
        this.a = g || 1;
      } else {
        this.r = r;
        this.g = g;
        this.b = b;
        this.a = a;
      }
    }
    blend(other, p) {
      let rgba = ['r', 'g', 'b', 'a'].map(c => (1 - p) * this[c] + p * other[c]);
      return new Colour(...rgba);
    }
    lighten(p) {
      let rgb = ['r', 'g', 'b'].map(c => 255 - p * (255 - this[c]));
      return new Colour(...rgb, this.a);
    }
    css() {
      return `rgba(${Math.round(this.r)}, ${Math.round(this.g)}, ${Math.round(this.b)}, ${this.a})`;
    }
  }
  Colour.colRE = /^#(..)(..)(..)$/;
  const barcss = {
    average: new Colour("#cccc80"),
    good: new Colour("#80ff80"),
    bad: new Colour("#ff8080"),
    live: new Colour("#e0ffe0"),
    down: new Colour("#ffffe0"),
    dead: new Colour("#ffe0e0"),
    disconnect: new Colour("#e0e0e0"),
    single: new Colour("#999999"),
    expStroke: new Colour("#8080ff").css(),
    expFill: new Colour("#8080ff", 0.5).css(),
  };
  const scaleColour = (val, avg, min, max, flip) => {
    let good = barcss.good;
    let bad = barcss.bad;
    if (flip) [good, bad] = [bad, good]
    if (val == avg) {
      return barcss.average;
    } else if (val < avg) {
      return bad.blend(barcss.average, 1 - (avg - val) / (avg - min));
    } else {
      return good.blend(barcss.average, 1 - (val - avg) / (max - avg));
    }
  }
  helpers.bar = (actual, average, min, max, top, flip) => {
    if (!average) return helpers.bar1(actual, top);

    if (min > actual) min = actual;
    if (max < actual) max = actual;
    top = Math.max(top || max, actual);
    let avgPct = average * 100 / top;
    let actPct = actual * 100 / top;
    let colour = scaleColour(actual, average, min, max, flip);
    let stroke = colour.css();
    let fill = colour.lighten(0.5).css();
    let svg = `
<svg xmlns='http://www.w3.org/2000/svg'>
<rect x='0%' width='${avgPct}%' y='10%' height='70%' stroke='${barcss.expStroke}' fill='${barcss.expFill}'/>
<rect x='0%' width='${actPct}%' y='20%' height='70%' stroke='${stroke}' fill='${fill}'/>
</svg>
    `.replace(/\n\s*/g, "");
    return `background-size: contain; background: url("data:image/svg+xml;utf8,${svg}")`
  };
  helpers.bar1 = (val, max) => {
    if (!max) return '';
    let actPct = val * 100 / max;
    let stroke = barcss.single.css();
    let fill = barcss.single.lighten(0.5).css();
    let svg = `
<svg xmlns='http://www.w3.org/2000/svg'>
<rect x='0%' width='${actPct}%' y='20%' height='70%' stroke='${stroke}' fill='${fill}'/>
</svg>
    `.replace(/\n\s*/g, "");
    return `background-size: contain; background: url("data:image/svg+xml;utf8,${svg}")`
  };
  helpers.barSurvivalPerc = (down_perc, dead_perc, disconnect_perc) => {
    let live_perc = 100 - (down_perc + dead_perc + disconnect_perc);
    let rects = [
      [live_perc, barcss.live],
      [down_perc, barcss.down],
      [dead_perc, barcss.dead],
      [disconnect_perc, barcss.disconnect]
    ];
    let rectSvg = [], x = 0;
    rects.forEach(([value, colour]) => {
      if (value) {
        rectSvg.push(`<rect x='${x}%' y='20%' height='70%' width='${value}%' fill='${colour.css()}'/>`);
        x += value;
      }
    });
    let svg = `
<svg xmlns='http://www.w3.org/2000/svg'>
${rectSvg.join("\n")}
</svg>
    `.replace(/\n\s*/g, "");
    return `background-size: contain; background: url("data:image/svg+xml;utf8,${svg}")`
  };
  helpers.barSurvival = (events, duration, numPlayers) => {
    switch (typeof numPlayers) {
      case "undefined":
        numPlayers = 1; break;
      case "object":
        numPlayers = Object.values(numPlayers).reduce((a, e) => a + e.members.length, 0);
    }
    let down_perc = (events.down_time || 0) * 100 / 1000 / numPlayers / duration;
    let dead_perc = (events.dead_time || 0) * 100 / 1000 / numPlayers / duration;
    let disconnect_perc = (events.disconnect_time || 0) * 100 / 1000 / numPlayers / duration;
    return helpers.barSurvivalPerc(down_perc, dead_perc, disconnect_perc);
  }
  helpers.p = (p) => {
    let b = atob(p);
    let p2 = new Uint8Array(400)
    for(var i = 0; i < 400; i++) {
        p2[i] = b.charCodeAt(i)
    }
    return new Float32Array(p2.buffer)
  }
  helpers.p_r = (p) => {
    let normalOrder = helpers.p(p);
    let reversed = [normalOrder[99]]
    for(let i = 1; i < 100; i++) {
      reversed.push(normalOrder[100-i])
    }
    return reversed;
  }
  helpers.p_bar = (p, max, space_for_image) => {
    let quantileColours = ['#d7191c', '#fdae61', '#2D81C6', '#BF326D', '#7B09C9']


    return helpers.svg(helpers.rectangle(0, 5, 80*p[99]/max, 30, new Colour(quantileColours[4]))
    + helpers.rectangle(0, 35, 80*p[90]/max, 30, new Colour(quantileColours[3]))
    + helpers.rectangle(0, 65, 80*p[50]/max, 30, new Colour(quantileColours[2]))
    + helpers.text(80*p[99]/max, 30, 11, helpers.num(p[99], 0))
    + helpers.text(80*p[90]/max, 60, 11, helpers.num(p[90], 0))
    + helpers.text(80*p[50]/max, 90, 11, helpers.num(p[50], 0)))
     + `;background-size: ${space_for_image ? 75 : 100}% 100%; background-position:${space_for_image ? 36 : 0}px 0px; background-repeat: no-repeat`;
  }
  helpers.rectangle = (x, y, width, height, colour) => {
    return `<rect x='${x}%' y='${y}%' height='${height}%' width='${width}%' fill='${colour.css()}'/>`
  }
  helpers.text = (x, y, size, text) => {
    return `<text x='${x}%' y='${y}%' font-family='Source Sans Pro' fill='#FCF1E2' font-size='${size}'>${text}</text>`
  }
  helpers.svg = (body) =>  {
    let svg = `
<svg xmlns='http://www.w3.org/2000/svg'>
${body}
</svg>`.replace(/\n\s*/g, "");
    return `background: url("data:image/svg+xml;utf8,${svg}")`
  }

  let loggedInPage = Object.assign({}, window.raidar_data.page);
  let initialPage = loggedInPage;
  const PERMITTED_PAGES = ['encounter', 'index', 'login', 'register', 'reset_pw', 'info-about', 'info-help', 'info-releasenotes', 'info-contact', 'global_stats', 'thank-you'];
  if (!window.raidar_data.username) {
    if (!initialPage.name) {
      loggedInPage = { name: 'info-releasenotes' };
      initialPage = { name: 'info-help' };
    } else if (PERMITTED_PAGES.indexOf(loggedInPage.name) == -1) {
      initialPage = { name: 'login' };
    }
  } else if (!initialPage.name) {
    initialPage = { name: 'info-releasenotes' };
  }
  let initData = {
    data: window.raidar_data,
    username: window.raidar_data.username,
    privacy: window.raidar_data.privacy,
    is_staff: window.raidar_data.is_staff,
    page: initialPage,
    persistent_page: { tab: 'combat_stats' },
    encounters: [],
    settings: {
      encounterSort: { prop: 'uploaded_at', dir: 'down', filters: false, filter: { success: null } },
    },
    uploads: [],
  };
  initData.data.boss_locations.forEach(loc => {
    loc.bosses = {}
    loc.wings.forEach(wing => wing.bosses.forEach(id => loc.bosses[id] = true ));
  });
  let lastNotificationId = window.raidar_data.last_notification_id;
  let storedSettingsJSON = localStorage.getItem('settings');
  if (storedSettingsJSON) {
    Object.assign(initData.settings, JSON.parse(storedSettingsJSON));
  }
  if (!initData.settings.comparePerc) initData.settings.comparePerc = 50;
  // TODO load from server
  initData.data.boons = [
    { boon: 'might', stacks: 25 },
    { boon: 'fury' },
    { boon: 'quickness' },
    { boon: 'alacrity' },
    { boon: 'protection' },
    { boon: 'retaliation' },
    { boon: 'regen' },
    { boon: 'aegis' },
    { boon: 'resist' },
    { boon: 'stab', stacks: 25 },
    { boon: 'swift' },
    { boon: 'vigor' },
    { boon: 'spotter' },
    { boon: 'glyph_of_empowerment' },
    { boon: 'spirit_of_frost' },
    { boon: 'sun_spirit' },
    { boon: 'stone_spirit' },
    { boon: 'storm_spirit' },
    { boon: 'empower_allies' },
    { boon: 'banner_strength' },
    { boon: 'banner_discipline' },
    { boon: 'banner_tactics' },
    { boon: 'banner_defence' },
    { boon: 'assassins_presence' },
    { boon: 'naturalistic_resonance' },
    { boon: 'pinpoint_distribution' },
    { boon: 'soothing_mist' },
    { boon: 'vampiric_presence' },
  ];
  delete window.raidar_data;

  function URLForPage(page) {
    let url = baseURL + page.name;
    if (page.no) url += '/' + page.no;
    if (page.era_id) url += '/' + page.era_id;
    if (page.area_id) url += '/area-' + page.area_id;
    return url;
  }

  function setData(data) {
    r.set(data);
    r.set('loading', false);
  }

  let pageInit = {
    login: page => {
      $('#login_username').select().focus();
    },
    register: page => {
      $('#register_username').select().focus();
    },
    reset_pw: page => {
      $('#reset_pw_email').select().focus();
    },
    encounter: page => {
      r.set({
        loading: true,
        "page.phase": 'All',
      });
      $.get({
        url: 'encounter/' + page.no + '.json',
      }).then(setData);
    },
    profile: page => {
      r.set({
        loading: true,
        'page.area': 'All raid bosses',
      });
      $.get({
        url: 'profile.json',
      }).then(setData).then(() => {
        let eras = r.get('profile.eras');
        let eraOrder = Object.values(eras)
          .filter(era => 'encounter' in era.profile)
          .sort((e1, e2) => e2.started_at - e1.started_at);
        r.set({
          'page.era': eraOrder[0].id,
          'profile.era_order': eraOrder,
        });
      });
    },
    global_stats: page => {
      r.set({
        loading: true,
      });
      $.get({
        url: URLForPage(page).substring(1) + '.json',
      }).then(setData);
    },
  };

  $(window).on('popstate', evt => {
    r.set('page', evt.originalEvent.state);
  });



  // Ractive
  let r = new Ractive({
    el: '#container',
    template: '#template',
    data: initData,
    computed: {
      changePassBad: function changePassBad() {
        let password = this.get('account.password'),
            password2 = this.get('account.password2');
        return password == '' || password !== password2;
      },
      encountersAreas: function encountersAreas() {
        let result = Array.from(new Set(this.get('encountersFiltered').map(e => e.area)));
        result.sort();
        return result;
      },
      encountersCharacters: function encountersCharacters() {
        let result = Array.from(new Set(this.get('encountersFiltered').map(e => e.character)));
        result.sort();
        return result;
      },
      encountersAccounts: function encountersAccounts() {
        let result = Array.from(new Set(this.get('encountersFiltered').map(e => e.account)));
        result.sort();
        return result;
      },
      encountersFiltered: function encountersFiltered() {
        let encounters = this.get('encounters') || [];
        let filters = this.get('settings.encounterSort.filter');
        const durRE = /^([0-9]+)(?::([0-5]?[0-9](?:\.[0-9]{,3})?)?)?/;
        const dateRE = /^(\d{4})(?:-(?:(\d{1,2})(?:-(?:(\d{1,2}))?)?)?)?$/;
        if (filters.success !== null) {
          encounters = encounters.filter(e => e.success === filters.success);
        }
        if (filters.area) {
          let f = filters.area.toLowerCase();
          encounters = encounters.filter(e => e.area.toLowerCase().startsWith(f));
        }
        if (filters.started_from) {
          let m = filters.started_from.match(dateRE);
          if (m) {
            let d = new Date(+m[1], (+m[2] - 1) || 0, +m[3] || 1);
            let f = d.getTime() / 1000;
            encounters = encounters.filter(e => e.started_at >= f);
          }
        }
        if (filters.started_till) {
          let m = filters.started_till.match(dateRE);
          if (m) {
            let d = new Date(+m[1], (+m[2] - 1) || 0, +m[3] || 1);
            if (m[3]) d.setDate(d.getDate() + 1);
            else if (m[2]) d.setMonth(d.getMonth() + 1);
            else if (m[1]) d.setFullYear(d.getFullYear() + 1);
            let f = d.getTime() / 1000;
            encounters = encounters.filter(e => e.started_at < f);
          }
        }
        if (filters.duration_from) {
          let m = filters.duration_from.match(durRE);
          if (m) {
            let f = ((+m[1] || 0) * 60 + (+m[2] || 0));
            encounters = encounters.filter(e => e.duration >= f);
          }
        }
        if (filters.duration_till) {
          let m = filters.duration_till.match(durRE);
          if (m) {
            let f = ((+m[1] || 0) * 60 + (+m[2] || 0));
            encounters = encounters.filter(e => e.duration <= f);
          }
        }
        if (filters.character) {
          let f = filters.character.toLowerCase();
          encounters = encounters.filter(e => e.character.toLowerCase().startsWith(f));
        }
        if (filters.account) {
          let f = filters.account.toLowerCase();
          encounters = encounters.filter(e => e.account.toLowerCase().startsWith(f));
        }
        if (filters.uploaded_from) {
          let m = filters.uploaded_from.match(dateRE);
          if (m) {
            let d = new Date(+m[1], (+m[2] - 1) || 0, +m[3] || 1);
            let f = d.getTime() / 1000;
            encounters = encounters.filter(e => e.uploaded_at >= f);
          }
        }
        if (filters.uploaded_till) {
          let m = filters.uploaded_till.match(dateRE);
          if (m) {
            let d = new Date(+m[1], (+m[2] - 1) || 0, +m[3] || 1);
            if (m[3]) d.setDate(d.getDate() + 1);
            else if (m[2]) d.setMonth(d.getMonth() + 1);
            else if (m[1]) d.setFullYear(d.getFullYear() + 1);
            let f = d.getTime() / 1000;
            encounters = encounters.filter(e => e.uploaded_at < f);
          }
        }
        if (filters.category !== null) {
          let f = filters.category;
          if (!f) f = null;
          encounters = encounters.filter(e => e.category === f);
        }
        if (filters.tag) {
          let f = filters.tag.toLowerCase();
          encounters = encounters.filter(e => e.tags.some(t => t.toLowerCase().startsWith(f)));
        }
        return encounters;
      },
      encounterSlice: function encounterSlice() {
        let encounters = this.get('encountersFiltered');
        let page = this.get('page.no') || 1;
        return encounters.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
      },
      encounterPages: function encounterPages() {
        let page = this.get('page.no') || 1;
        let encounters = this.get('encountersFiltered') || [];
        let totalPages = Math.ceil(encounters.length / PAGE_SIZE);
        let minPage = Math.max(2, page - PAGINATION_WINDOW);
        let maxPage = Math.min(totalPages - 1, page + PAGINATION_WINDOW);
        let pages = []

        pages.push({t: "<", c: 'uk-pagination-previous', d: 1 == page, n: page - 1})
        pages.push({t: 1, a: 1 == page});
        if (minPage > 2) pages.push({t: '...', d: true});
        let i;
        for (i = minPage; i <= maxPage; i++) pages.push({t: i, a: i == page});
        if (maxPage < totalPages - 1) pages.push({t: '...', d: true});
        if (maxPage < totalPages && totalPages != 1) pages.push({t: totalPages, a: totalPages == page});
        pages.push({t: ">", c: 'uk-pagination-next', d: totalPages == page, n: page + 1});
        return pages;
      },
    },
    delimiters: ['[[', ']]'],
    tripleDelimiters: ['[[[', ']]]'],
    page: setPage,
  });

  r.observe('settings', (newValue, oldValue, keyPath) => {
    localStorage.setItem('settings', JSON.stringify(newValue));
  });

  // history, pushState
  function setPage(page) {
    if (typeof page == "string") {
      page = { name: page };
    }
    if (typeof page == "undefined") {
      page = r.get('page');
    } else {
      r.set('page', page);
    }
    let url = URLForPage(page);
    history.pushState(page, null, url);
    if (pageInit[page.name]) {
      pageInit[page.name](page);
    }
    if (window.ga) {
      window.ga('set', 'page', url);
      window.ga('send', 'pageview');
    }
    return false;
  }
  let url = URLForPage(initData.page);
  history.replaceState(initData.page, null, url);
  if (pageInit[initData.page.name]) {
    pageInit[initData.page.name](initData.page);
  }
  if (window.ga) {
    window.ga('set', 'page', url);
    window.ga('send', 'pageview');
  }



  function notification(str, style) {
    UIkit.notification(str, style);
  }

  function error(str) {
    notification(str, 'danger')
  }
  function success(str) {
    UIkit.notification(str, {
      status: 'success',
    });
  }

  function sortEncounters() {
    let currentProp = r.get('settings.encounterSort.prop');
    let currentDir = r.get('settings.encounterSort.dir');
    r.get('encounters').sort((currentDir == 'up' ? ascSort : descSort)(currentProp));
    r.update('encounters');
  }

  function updateRactiveFromResponse(response) {
    r.set(response);
    sortEncounters();
  }

  // test for shenanigans
  $.ajax({
    url: 'initial.json',
  }).done(updateRactiveFromResponse);



  function didLogin(response) {
    if (response.error) {
      error(response.error);
    } else {
      r.set({
        'auth.input.username': '',
        'auth.input.password': '',
        'auth.input.password2': '',
        'auth.input.api_key': '',
      });
      setPage(response.page || loggedInPage);
      csrftoken = response.csrftoken;
      delete response.csrftoken;
      updateRactiveFromResponse(response);
    }
  }

  function graphLine(value, data) {
    let ary = Array(data.length);
    ary[0] = ary[data.length - 1] = value;
    return ary;
  }

  function graphLineDataset(label, value, borderDash, backgroundColor, borderColor, data) {
    return {
      label: label,
      data: graphLine(value, data),
      spanGaps: true,
      borderDash: borderDash,
      pointRadius: 0,
      backgroundColor: backgroundColor,
      borderColor: borderColor,
      borderWidth: 2,
    };
  };

  const ascSort = (prop) => (a, b) =>
    a[prop] > b[prop] ? 1 :
    a[prop] < b[prop] ? -1 : 0;
  const descSort = (prop) => (a, b) =>
    a[prop] < b[prop] ? 1 :
    a[prop] > b[prop] ? -1 : 0;


  r.on({
    encounter_bug: function encounterBug(x) {
      let url = r.get('encounter.url_id');
      r.set('contact.input.subject', `Error report: ${url}`);
      setPage('info-contact');
      return false;
    },
    refresh_page: function refreshPage(x) {
      setPage();
    },
    auth_login: function login(x) {
      if (!x.element.node.form.checkValidity()) return;

      let username = this.get('auth.input.username'),
          password = this.get('auth.input.password');

      $.post({
        url: 'login.json',
        data: {
          username: username,
          password: password,
        },
      }).done(didLogin);

      return false;
    },
    auth_register: function register(x) {
      if (!x.element.node.form.checkValidity()) return;

      let username = this.get('auth.input.username'),
          password = this.get('auth.input.password'),
          apiKey = this.get('auth.input.api_key'),
          email = this.get('auth.input.email');

      $.post({
        url: 'register.json',
        data: {
          username: username,
          password: password,
          api_key: apiKey,
          email: email,
        },
      }).done(didLogin);

      return false;
    },
    auth_reset_pw: function resetPw(x) {
      if (!x.element.node.form.checkValidity()) return;

      let email = this.get('auth.input.email');

      $.post({
        url: 'reset_pw.json',
        data: {
          email: email,
        },
      }).done(() => {
        notification('Sending now.', 'primary')
      })

      return false;
    },
    auth_logout: function logout() {
      $.post({
        url: 'logout.json',
      }).done(response => {
        this.set({
          username: null,
        });
        setPage('info-help');
      });
    },
    page_no: function pageNo(evt) {
      let page_no = parseInt(evt.node.getAttribute('data-page'));
      let page = this.get('page');
      setPage(Object.assign(page, { no: page_no }));
      return false;
    },
    change_password: function changePassword(x) {
      if (!x.element.node.form.checkValidity()) return;

      $.post({
        url: 'change_password.json',
        data: {
          old_password: r.get('account.old_password'),
          new_password1: r.get('account.password'),
          new_password2: r.get('account.password2'),
        },
      }).done(response => {
        if (response.error) {
          error(response.error);
        } else {
          success('Password changed');
          r.set('account.old_password', '');
          r.set('account.password', '');
          r.set('account.password2', '');
        }
      });
      return false;
    },
    change_email: function changeEmail(x) {
      if (!x.element.node.form.checkValidity()) return;

      $.post({
        url: 'change_email.json',
        data: {
          email: r.get('account.email'),
        },
      }).done(response => {
        if (response.error) {
          error(response.error);
        } else {
          success('Email changed');
          r.set('account.email', '');
        }
      });
      return false;
    },
    add_api_key: function addAPIKey(x) {
      if (!x.element.node.form.checkValidity()) return;

      let api_key = r.get('account.api_key');
      $.post({
        url: 'add_api_key.json',
        data: {
          api_key: api_key,
        },
      }).done(response => {
        if (response.error) {
          error(response.error);
        } else {
          success(`API key for ${response.account_name} added`);
          r.set('account.api_key', '');
          let accounts = r.get('accounts');
          let account = accounts.find(account => account.name == response.account_name);
          let len = api_key.length;
          api_key = api_key.substring(0, 8) +
                    api_key.substring(8, len - 12).replace(/[0-9a-zA-Z]/g, 'X') +
                    api_key.substring(len - 12);
          if (account) {
            account.api_key = api_key;
          } else {
            accounts.push({ name: response.account_name, api_key: api_key });
          }
          r.update('accounts');
        }
      });
      return false;
    },
    contact_us: function contactUs(x) {
      if (!x.element.node.form.checkValidity()) return;

      let data = r.get('contact.input');

      $.post({
        url: 'contact.json',
        data: data
      }).done(response => {
        if (response.error) {
          error(response.error);
        } else {
          success('Email sent');
          r.set('contact.input', {});
        }
      });

      return false;
    },
    sort_encounters: function sortEncountersChange(evt) {
      let currentProp = r.get('settings.encounterSort.prop');
      let currentDir = r.get('settings.encounterSort.dir');
      let newSort = $(evt.node).closest('th').data('sort');
      let [clickedProp, clickedDir] = newSort.split(':');
      if (clickedProp == currentProp) {
        currentDir = currentDir == 'up' ? 'down' : 'up';
        r.set('settings.encounterSort.dir', currentDir);
      } else {
        currentProp = clickedProp;
        currentDir = clickedDir;
        r.set('settings.encounterSort.prop', clickedProp);
        r.set('settings.encounterSort.dir', clickedDir);
      }
      sortEncounters();
      return false;
    },
    encounter_filter_toggle: function encounterFilterToggle(evt) {
      let filters = r.get('settings.encounterSort.filters');
      r.toggle('settings.encounterSort.filters');
      if (filters) {
        r.set('settings.encounterSort.filter.*', null);
      }
      return false;
    },
    encounter_filter_success: function encounterFilterSuccess(evt) {
      r.set('settings.encounterSort.filter.success', JSON.parse(evt.node.value));
      return false;
    },
    privacy: function privacy(evt) {
      let privacy = r.get('privacy');
      $.post({
        url: 'privacy.json',
        data: {
          privacy: privacy,
        },
      }).done(() => {
        notification('Privacy updated.', 'success');
      });
    },
    set_tags_cat: function setTags(evt) {
      let encounter = r.get('encounter');

      $.post({
        url: 'set_tags_cat.json',
        data: {
          id: encounter.id,
          tags: encounter.tags,
          category: encounter.category,
        },
      }).done(() => {
        let eRowId = r.get('encounters').findIndex(e => e.id == encounter.id);
        let eRow = r.get('encounters.' + eRowId);
        eRow.category = encounter.category;
        eRow.tags = encounter.tags.split(',');
        r.update('encounters.' + eRowId);

        notification('Category and tags saved.', 'success');
      });
      return false;
    },
    chart: function chart(evt, archetype, profession, elite, stat, statName) {
      let eraId = r.get('page.era');
      let eras = r.get('profile.eras');
      let areaId = r.get('page.area');
      let archetypeName = archetype == 'All' ? '' : r.get('data.archetypes')[archetype] + ' ';
      let charDescription = profession == 'All' ? `All ${archetypeName}specialisations'` : archetypeName + r.get('data.specialisations')[profession][elite];
      let areaName = r.get('data.areas')[areaId] || areaId;

      $.post({
        url: 'profile_graph.json',
        data: {
          era: eraId,
          area: areaId,
          archetype: archetype,
          profession: profession,
          elite: elite,
          stat: stat,
        },
      }).then(payload => {
        let {globals, data, times} = payload;
        times = times.map(time => helpers.formatDate(time));
        let pointRadius = 4;
        if (data.length == 1) {
          data = [data[0], data[0], data[0]];
          times = ['', times[0], ''];
          pointRadius = [0, pointRadius, 0];
        }

        let height = Math.round(window.innerHeight * 0.80);
        let width = Math.round(window.innerWidth * 0.80);
        let dialog = UIkit.modal.dialog(`
<button class="uk-modal-close-outside" uk-transition-hide type="button" uk-close></button>
<div>
<canvas height="${height}" width="${width}"/>
</div>
            `, {center: true});
        $(dialog.$el).css('overflow', 'hidden').addClass('uk-modal-lightbox');
        $(dialog.panel).css({width: width, height: height});
        dialog.caption = $('<div class="uk-modal-caption" uk-transition-hide></div>').appendTo(dialog.panel);
        let ctx = $(dialog.$el).find('canvas');
        let datasets = [];
        if (globals) {
          datasets.push(graphLineDataset('P99', globals.per[99], [1, 1], "rgba(255, 255, 255, 0)", "rgba(128, 128, 128, 1)", data));
          datasets.push(graphLineDataset('P90', globals.per[90], [4, 4], "rgba(255, 255, 255, 0)", "rgba(128, 128, 128, 1)", data));
          datasets.push(graphLineDataset('P50', globals.per[50], [7, 7], "rgba(255, 255, 255, 0)", "rgba(128, 128, 128, 1)", data));
          datasets.push(graphLineDataset('avg', globals.avg, undefined, "rgba(255, 255, 255, 0)", "rgba(255, 0, 255, 1)", data));
        }
        datasets.push({
          label: statName,
          data: data,
          backgroundColor: "rgba(0, 0, 0, 0.05)",
          borderColor: "rgba(0, 0, 0, 1)",
          pointBackgroundColor: "rgba(255, 255, 255, 1)",
          pointRadius: pointRadius,
        });
        let chart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: times,
            datasets: datasets,
          },
          options: {
            title: {
              text: `${charDescription} ${statName} on ${areaName}`,
              display: true,
            },
            scales: {
              yAxes: [{
                ticks: {
                  beginAtZero: true
                }
              }]
            }
          }
        });
      });
    },
  });



  let uploadProgressHandler = (entry, evt) => {
    let progress = Math.round(100 * evt.loaded / evt.total);
    //if (evt.loaded == evt.total) {
    //}
    entry.progress = progress;
    r.update('uploads');
  }
  let uploadProgressDone = (entry, data) => {
    if (data.error) {
      entry.error = data.error;
      uploadProgressFail(entry);
    } else {
      entry.upload_id = data.upload_id;
    }
    delete entry.file;
    r.update('uploads');
    startUpload(true);
  }

    // if (data.error) {
    //   entry.error = data.error;
    //   error(entry.name + ': ' + data.error);
    //   uploadProgressFail(entry);
    // } else {
    //   if (data.encounter) {
    //     let encounters = r.get('encounters');
    //     encounters = encounters.filter(encounter => encounter.id != data.id)
    //     encounters.push(data.encounter);
    //     updateRactiveFromResponse({ encounters: encounters });
    //   }

    //   entry.encounterId = data.id;
    //   entry.success = true;
    //   delete entry.file;
    //   r.update('uploads');
    //   startUpload(true);
    // }

  let uploadProgressFail = entry => {
    entry.success = false;
    delete entry.file;
    r.update('uploads');
    startUpload(true);
  }

  let makeXHR = entry => {
    let req = $.ajaxSettings.xhr();
    req.upload.addEventListener("progress", uploadProgressHandler.bind(null, entry), false);
    return req;
  }

  let uploading = null;
  function startUpload(previousIsFinished) {
    if (uploading && !previousIsFinished) return;

    let entry = r.get('uploads').find(entry => !("progress" in entry));
    uploading = entry;
    if (!entry) return;

    let form = new FormData();
    form.set('file', entry.file);
    let category = r.get('upload.category');
    if (category) {
      form.set('category', category);
    }
    let tags = r.get('upload.tags');
    if (tags) {
      form.set('tags', r.get('upload.tags'));
    }
    return $.ajax({
      url: 'upload.json',
      data: form,
      type: 'POST',
      contentType: false,
      processData: false,
      xhr: makeXHR.bind(null, entry),
    })
    .done(uploadProgressDone.bind(null, entry))
    .fail(uploadProgressFail.bind(null, entry));
  }

  const notificationHandlers = {
    upload: notification => {
      //let entry = uploads.find(entry => entry.upload_id == notification.upload_id);
      let entry = r.get('uploads').find(entry => entry.name == notification.filename);
      let newEntry = {
        name: notification.filename,
        progress: 100,
        upload_id: notification.upload_id,
        uploaded_by: notification.uploaded_by,
        success: true,
        encounterId: notification.encounter_id,
        encounterUrlId: notification.encounter_url_id,
      };
      if (entry) {
        Object.assign(entry, newEntry);
        r.update('uploads');
      } else {
        r.push('uploads', newEntry);
      }

      let encounters = r.get('encounters');
      encounters = encounters.filter(encounter => encounter.id != notification.encounter_id)
      if (notification.encounter) {
        encounters.push(notification.encounter);
      }
      updateRactiveFromResponse({ encounters: encounters });
    },
    upload_error: notification => {
      let uploads = r.get('uploads');
      let entry = uploads.find(entry => entry.upload_id == notification.upload_id);
      if (entry) {
        entry.success = false;
        entry.error = notification.error;
        r.update('uploads');
      }
    },
  };

  function handleNotification(notification) {
    let handler = notificationHandlers[notification.type];
    if (!handler) { // sanity check
      console.error("No handler for notification type " + notification.type);
      return;
    }
    handler(notification);
  }

  function upgradeClient() {
    notification('Server was upgraded, client will restart in <span id="upgrade-countdown"></span>s', { status: 'warning', timeout: 10000 });
    let count = 8;
    let cdEl = document.getElementById('upgrade-countdown');
    let loop = () => {
      cdEl.textContent = --count;
      if (count) {
        setTimeout(loop, 1000);
      } else {
        window.location.reload(true);
      }
    };
    setTimeout(loop, 1000);
  }

  const POLL_TIME = 10000;
  function pollNotifications() {
    if (r.get('username')) {
      let options = {
        url: 'poll.json',
        type: 'POST',
      }
      if (lastNotificationId) {
        options.data = { last_id: lastNotificationId };
      }
      $.ajax(options).done(data => {
        if (data.last_id) {
          lastNotificationId = data.last_id;
        }
        data.notifications.forEach(handleNotification);
        if (data.version != r.get('data.version.id')) {
          upgradeClient();
        }
      }).always(() => {
        setTimeout(pollNotifications, POLL_TIME);
      });
    } else {
      setTimeout(pollNotifications, POLL_TIME);
    }
  };
  pollNotifications();


  $(document)
    .on('dragstart dragover dragenter', evt => {
      if (r.get('username')) {
        evt.originalEvent.dataTransfer.effectAllowed = "copyMove";
        evt.originalEvent.dataTransfer.dropEffect = "copy";
      } else {
        evt.originalEvent.dataTransfer.effectAllowed = "none";
        evt.originalEvent.dataTransfer.dropEffect = "none";
      }
      evt.stopPropagation()
      evt.preventDefault();
    })
    .on('drop', evt => {
      if (!r.get('username')) return;

      let files = evt.originalEvent.dataTransfer.files;
      let jQuery_xhr_factory = $.ajaxSettings.xhr;
      Array.from(files).forEach(file => {
        if (!file.name.endsWith('.evtc') && !file.name.endsWith('.evtc.zip')) return;
        let entry = r.get('uploads').find(entry => entry.name == file.name);
        if (entry) {
          delete entry.success;
          delete entry.progress;
          entry.file = file;
          r.update('uploads');
        } else {
          r.push('uploads', {
            name: file.name,
            file: file,
            uploaded_by: r.get('username'),
          });
        }
        startUpload();
      });
      setPage('uploads');
      evt.preventDefault();
    });


  if (DEBUG) window.r = r; // XXX DEBUG Ractive
})();
