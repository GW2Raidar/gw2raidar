"use strict";

// XAcquire Django CSRF token for AJAX, and prefix the base URL
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
  $(document).ajaxError(evt => error("Error connecting to server"))


  let helpers = Ractive.defaults.data;
  helpers.formatDate = timestamp => {
    let date = new Date(timestamp * 1000);
    return date.toISOString().replace('T', ' ').replace(/.000Z$/, '');
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
  helpers.bar = (actual, average, min, max, top) => {
    if (!top) top = max;
    let avgPct = average * 100 / top;
    let actPct = actual * 100 / top;
    let colour = scaleColour(actual, average, min, max);
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
    console.log(val, max);
  };

  let loggedInPage = Object.assign({}, window.raidar_data.page);
  let initData = {
    data: window.raidar_data,
    username: window.raidar_data.username,
    is_staff: window.raidar_data.is_staff,
    page: window.raidar_data.username ? loggedInPage : { name: 'index' },
    encounters: [],
  };
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
      encounterSlice: function encounterSlice() {
        let page = this.get('page.no') || 1;
        let encounters = this.get('encounters') || [];
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
      }
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
    history.pushState(page, null, URLForPage(page));
    if (pageInit[page.name]) {
      pageInit[page.name](page);
    }
    return false;
  }
  history.replaceState(initData.page, null, URLForPage(initData.page));
  if (pageInit[initData.page.name]) {
    pageInit[initData.page.name](initData.page);
  }



  function error(str) {
    UIkit.notification(str, {
      status: 'danger',
    });
  }

  function updateRactiveFromResponse(response) {
    if (response.encounters) {
      response.encounters.sort((a, b) => b.started_at - a.started_at);
    }
    r.set(response);
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
  });



  let uploadProgressHandler = (file, evt) => {
    let progress = Math.round(100 * evt.loaded / evt.total);
    // TODO single upload progress
  }
  let uploadProgressDone = (file, data) => {
    if (data.error) {
      error(file.name + ': ' + data.error);
    } else {
      let encounters = r.get('encounters');
      let fileNames = Object.keys(data);
      let newKeys = fileNames.map(file => data[file].id)
      encounters = encounters.filter(encounter => newKeys.indexOf(encounter.id) == -1)
      fileNames.forEach(file => encounters.push(data[file]));
      updateRactiveFromResponse({ encounters: encounters });
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
      let promises = Array.from(files).map(file => {
        if (!file.name.endsWith('.evtc')) return;
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
      $.when(promises).then(results => {
        // TODO all done
      });
      evt.preventDefault();
    });

  window.r = r; // XXX DEBUG
})();
