"use strict";

// Acquire Django CSRF token for AJAX, and prefix the base URL
(function setupAjaxForAuth() {
  const PAGE_SIZE = 10;
  const PAGINATION_WINDOW = 5;

  const DEBUG = raidar_data.debug;
  Ractive.DEBUG = DEBUG;


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
    error("Error communicating to server")
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
    if (metricData.data_type == 0) {
      value = "[" + helpers.formatTime(value / 1000) + "]";
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

  let loggedInPage = Object.assign({}, window.raidar_data.page);
  let initialPage = loggedInPage;
  const PERMITTED_PAGES = ['encounter', 'index', 'login', 'register', 'reset_pw', 'info-about', 'info-help', 'info-releasenotes', 'info-contact'];
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
    upload: [],
  };
  let lastNotificationId = window.raidar_data.last_notification_id;
  let storedSettingsJSON = localStorage.getItem('settings');
  if (storedSettingsJSON) {
    Object.assign(initData.settings, JSON.parse(storedSettingsJSON));
  }
  initData.data.boons = [
    { boon: 'might', stacks: 25 },
    { boon: 'fury' },
    { boon: 'quickness' },
    { boon: 'alacrity' },
    { boon: 'protection' },
    { boon: 'retaliation' },
    { boon: 'spotter' },
    { boon: 'glyph_of_empowerment' },
    { boon: 'gotl', stacks: 5 },
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
        let latest = eras[eras.length - 1];
        r.set({
          'page.era': latest,
        });
      });
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
    r.set('page', page);
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
        notification('Category and tags saved.', 'success');
      });
      return false;
    },
  });



  let uploadProgressHandler = (entry, evt) => {
    let progress = Math.round(100 * evt.loaded / evt.total);
    //if (evt.loaded == evt.total) {
    //}
    entry.progress = progress;
    r.update('upload');
  }
  let uploadProgressDone = (entry, data) => {
    if (data.error) {
      entry.error = data.error;
      uploadProgressFail(entry);
    } else {
      entry.upload_id = data.upload_id;
    }
    delete entry.file;
    r.update('upload');
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
    //   r.update('upload');
    //   startUpload(true);
    // }

  let uploadProgressFail = entry => {
    entry.success = false;
    delete entry.file;
    r.update('upload');
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

    let entry = r.get('upload').find(entry => !("progress" in entry));
    uploading = entry;
    if (!entry) return;

    let form = new FormData();
    form.append(entry.name, entry.file);
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
      let entry = r.get('upload').find(entry => entry.name == notification.filename);
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
        r.update('upload');
      } else {
        r.push('upload', newEntry);
      }

      let encounters = r.get('encounters');
      encounters = encounters.filter(encounter => encounter.id != notification.encounter_id)
      if (notification.encounter) {
        encounters.push(notification.encounter);
      }
      updateRactiveFromResponse({ encounters: encounters });
    },
    upload_error: notification => {
      let uploads = r.get('upload');
      let entry = uploads.find(entry => entry.upload_id == notification.upload_id);
      if (entry) {
        entry.success = false;
        entry.error = notification.error;
        r.update('upload');
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
      }).then(() => {
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
        let entry = r.get('upload').find(entry => entry.name == file.name);
        if (entry) {
          delete entry.success;
          delete entry.progress;
          entry.file = file;
          r.update('upload');
        } else {
          r.push('upload', {
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
