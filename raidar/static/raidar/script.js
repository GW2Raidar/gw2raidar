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


  var helpers = Ractive.defaults.data;
  helpers.formatDate = timestamp => {
    let date = new Date(timestamp * 1000);
    return date.toISOString().replace('T', ' ').replace(/.000Z$/, '');
  }

  let initData = {
    data: window.raidar_data,
    username: window.raidar_data.username,
    is_staff: window.raidar_data.is_staff,
    page: { name: window.raidar_data.username ? 'encounters' : 'index' },
    encounters: [],
  };
  delete window.raidar_data;


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

    page: function(page, field) {
      this.set('page', { name: page });
      if (field) {
        $('#' + field).select().focus();
      }
    },
  });
  window.r = r; // XXX DEBUG


  let errorAnimation;
  function error(str) {
    if (errorAnimation) errorAnimation.stop();

    r.set('error', {
      message: str,
      opacity: 1,
    });

    errorAnimation = r.animate('error.opacity', 0, {
      duration: 5000,
      easing: 'easeIn',
    })
    errorAnimation.then(() => {
      errorAnimation = null;
      r.set('error', {})
    })
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
        'page.name': 'encounters'
      });
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
        url: 'login',
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
          email = this.get('auth.input.email');

      $.post({
        url: 'register',
        data: {
          username: username,
          password: password,
          email: email,
        },
      }).done(didLogin);

      return false;
    },
    auth_logout: function logout() {
      $.post({
        url: 'logout',
      }).done(response => {
        this.set({
          username: null,
          'page.name': 'index',
        });
      });
    },
    page_no: function pageNo(evt) {
      this.set('page.no', parseInt(evt.node.getAttribute('data-page')));
      return false;
    },
  });



  let uploadProgressHandler = (file, evt) => {
    let progress = Math.round(100 * evt.loaded / evt.total);
    // TODO single upload progress
  }
  let uploadProgressDone = (file, data) => {
    let encounters = r.get('encounters');
    let newKeys = Object.keys(data);
    encounters = encounters.filter(encounter => newKeys.indexOf(encounter.id) == -1)
    newKeys.forEach(file => encounters.push(data[file]));
    updateRactiveFromResponse({ encounters: encounters });
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
        let form = new FormData();
        form.append(file.name, file);
        return $.ajax({
          url: 'upload',
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
})();
