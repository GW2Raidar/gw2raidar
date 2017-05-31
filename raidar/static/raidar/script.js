"use strict";

// Acquire Django CSRF token for AJAX, and prefix the base URL
(function setupAjaxForAuth() {

  const PAGE_SIZE = 10;
  const PAGINATION_WINDOW = 5;

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
  helpers.formatDate = timestamp => {
    if (timestamp) {
      let date = new Date(timestamp * 1000);
      return `${date.getFullYear()}-${f0X(date.getMonth() + 1)}-${f0X(date.getDate())} ${f0X(date.getHours())}:${f0X(date.getMinutes())}:${f0X(date.getSeconds())}`;
    } else {
      return '';
    }
  };
  helpers.formatTime = duration => {
    if (duration) {
      let seconds = Math.trunc(duration);
      let minutes = Math.trunc(seconds / 60);
      let usec = Math.trunc((duration - seconds) * 1000);
      seconds -= minutes * 60
      if (usec < 10) usec = "00" + usec;
      else if (usec < 100) usec = "0" + usec;
      return minutes + ":" + f0X(seconds) + "." + usec;
    } else {
      return '';
    }
  };
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
      let rgba = ['r', 'g', 'b', 'a'].map(c => 255 - p * (255 - this[c]));
      return new Colour(...rgba);
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
    single: new Colour("#999999"),
    expStroke: new Colour("#8080ff").css(),
    expFill: new Colour("#8080ff", 0.5).css(),
  };
  const scaleColour = (val, avg, min, max) => {
    if (val == avg) {
      return barcss.average;
    } else if (val < avg) {
      return barcss.bad.blend(barcss.average, 1 - (avg - val) / (avg - min));
    } else {
      return barcss.good.blend(barcss.average, 1 - (val - avg) / (max - avg));
    }
  }
  helpers.bar = (actual, average, min, max, top, flip) => {
  if(flip)console.log(actual, average, min, max, top, flip)
    if (min > actual) min = actual;
    if (max < actual) max = actual;
    top = Math.max(top || max, actual);
    let avgPct = average * 100 / top;
    let actPct = actual * 100 / top;
    let colour = scaleColour(actual, average, flip ? max : min, flip ? min : max);
    let stroke = colour.css();
    let fill = colour.lighten(0.5).css();
    if(flip)console.log(fill)
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

  let loggedInPage = Object.assign({}, window.raidar_data.page);
  let initData = {
    data: window.raidar_data,
    username: window.raidar_data.username,
    is_staff: window.raidar_data.is_staff,
    page: window.raidar_data.username ? loggedInPage : { name: 'index' },
    encounters: [],
    encounterSort: { prop: 'uploaded_at', dir: 'down', filters: false, filter: { success: null } },
    upload: {}, // 1: uploading, 2: analysing, 3: done, 4: rejected
  };
  initData.data.boons = [
    { boon: 'might', stacks: 25 },
    { boon: 'fury' },
    { boon: 'quickness' },
    { boon: 'alacrity' },
    { boon: 'protection' },
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
        "page.tab": 'combat_stats',
        "page.phase": 'All',
      });
      $.get({
        url: 'encounter/' + page.no + '.json',
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
      authBad: function authBad() {
        let username = this.get('auth.input.username'),
            password = this.get('auth.input.password'),
            email = this.get('auth.input.email');

        let authOK = username != '' && password != '';
        if (this.get('page.name') == 'register') {
          let password2 = this.get('auth.input.password2');
          let emailOK = email != ''; // TODO maybe basic pattern check
          authOK = authOK && password == password2 && emailOK;
        }
        return !authOK;
      },
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
        let filters = this.get('encounterSort.filter');
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
        let encounters = this.get('encounters') || [];
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
      uploadsByState: function uploadsByState() {
        let states = this.get('upload');
        let files = { 1: [], 2: [], 3: [], 4: [] };
        Object.keys(states).forEach(fileName => {
          files[states[fileName]].push(fileName);
        });
        return files;
      },
    },
    delimiters: ['[[', ']]'],
    tripleDelimiters: ['[[[', ']]]'],
    page: setPage,
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
    let currentProp = r.get('encounterSort.prop');
    let currentDir = r.get('encounterSort.dir');
    r.get('encounters').sort((currentDir == 'up' ? ascSort : descSort)(currentProp));
    r.update('encounters');
  }

  function updateRactiveFromResponse(response) {
    r.set(response);
    sortEncounters();
  }

  // test for shenanigans
  $.ajax({
    url: 'initial',
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
    auth_login: function login() {
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
    auth_register: function register() {
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
    auth_reset_pw: function resetPw() {
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
        setPage('index');
      });
    },
    page_no: function pageNo(evt) {
      let page_no = parseInt(evt.node.getAttribute('data-page'));
      let page = this.get('page');
      setPage(Object.assign(page, { no: page_no }));
      return false;
    },
    change_password: function changePassword(evt) {
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
    change_email: function changeEmail(evt) {
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
    add_api_key: function addAPIKey(evt) {
      $.post({
        url: 'add_api_key.json',
        data: {
          api_key: r.get('account.api_key'),
        },
      }).done(response => {
        if (response.error) {
          error(response.error);
        } else {
          success(`API key for ${response.account_name} added`);
          r.set('account.api_key', '');
        }
      });
      return false;
    },
    sort_encounters: function sortEncountersChange(evt) {
      let currentProp = r.get('encounterSort.prop');
      let currentDir = r.get('encounterSort.dir');
      let [clickedProp, clickedDir] = evt.node.getAttribute('data-sort').split(':');
      if (clickedProp == currentProp) {
        currentDir = currentDir == 'up' ? 'down' : 'up';
        r.set('encounterSort.dir', currentDir);
      } else {
        currentProp = clickedProp;
        currentDir = clickedDir;
        r.set('encounterSort.prop', clickedProp);
        r.set('encounterSort.dir', clickedDir);
      }
      sortEncounters();
    },
    encounter_filter_toggle: function encounterFilterToggle(evt) {
      r.toggle('encounterSort.filters');
      return false;
    },
    encounter_filter_success: function encounterFilterSuccess(evt) {
      r.set('encounterSort.filter.success', JSON.parse(evt.node.value));
      console.log(r.get('encounterSort.filter.success'));
      return false;
    },
  });



  let uploadProgressHandler = (file, evt) => {
    // let progress = Math.round(100 * evt.loaded / evt.total);
    if (evt.loaded == evt.total) {
      r.get('upload')[file.name] = 2;
      r.update('upload');
    }
  }
  let uploadProgressDone = (file, data) => {
    if (data.error) {
      error(file.name + ': ' + data.error);

      r.get('upload')[file.name] = 4;
      r.update('upload');
    } else {
      let encounters = r.get('encounters');
      let fileNames = Object.keys(data);
      let newKeys = fileNames.map(file => data[file].id)
      encounters = encounters.filter(encounter => newKeys.indexOf(encounter.id) == -1)
      fileNames.forEach(file => encounters.push(data[file]));
      updateRactiveFromResponse({ encounters: encounters });

      r.get('upload')[file.name] = 3;
      r.update('upload');
    }
  }

  let makeXHR = file => {
    let req = $.ajaxSettings.xhr();
    req.upload.addEventListener("progress", uploadProgressHandler.bind(null, file), false);
    return req;
  }

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

        r.get('upload')[file.name] = 1;
        r.update('upload');

        let form = new FormData();
        form.append(file.name, file);
        return $.ajax({
          url: 'upload.json',
          data: form,
          type: 'POST',
          contentType: false,
          processData: false,
          xhr: makeXHR.bind(null, file),
        })
        .done(uploadProgressDone.bind(null, file));
      });
      evt.preventDefault();
    });

  window.r = r; // XXX DEBUG
})();
