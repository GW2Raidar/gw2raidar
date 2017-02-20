"use strict";

// XAcquire Django CSRF token for AJAX, and prefix the base URL
(function setupAjaxForAuth() {
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
    username: window.userprops.username,
    is_staff: window.userprops.is_staff,
    auth: {
      login: true,
    },
    page: { name: 'index' },
    encounters: [],
  };


  // Ractive
  let r = new Ractive({
    el: '#container',
    template: '#template',
    data: initData,
    computed: {
      'authBad': function authBad() {
        let username = this.get('auth.input.username'),
            password = this.get('auth.input.password'),
            email = this.get('auth.input.email');

        let authOK = username != '' && password != '';
        if (!this.get('auth.login')) {
          let password2 = this.get('auth.input.password2');
          let emailOK = email != ''; // TODO maybe basic pattern check
          authOK = authOK && password == password2 && emailOK;
        }
        return !authOK;
      },
    },
    delimiters: ['[[', ']]'],
    tripleDelimiters: ['[[[', ']]]']
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


  // test for shenanigans
  $.ajax({
    url: 'initial',
  }).done(response => {
    response.encounters.sort((a, b) => b.started_at - a.started_at);
    r.set(response);
  });



  function didLogin(response) {
    if (response.error) {
      error(response.error);
    } else {
      r.set({
        'auth.input.username': '',
        'auth.input.password': '',
        'auth.input.password2': '',
      });
      csrftoken = response.csrftoken;
      delete response.csrftoken;
      r.set(response);
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
    },
    auth_logout: function logout() {
      $.post({
        url: 'logout',
      }).done(response => {
        this.set({
          username: null,
          'auth.login': true,
        });
      });
    },
    auth_swap: function swap() {
      this.set({
        'auth.login': !this.get('auth.login'),
        'auth.input.password': '',
        'auth.input.password2': '',
      });
    },
    to_profile: function toProfile() {
      r.set('page', { name: 'profile' })
    },
  });



  let uploadProgressHandler = (file, evt) => {
    let progress = Math.round(100 * evt.loaded / evt.total);
    // TODO single upload progress
  }
  let uploadProgressDone = (file, data) => {
    let encounters = r.get('encounters');
    Object.keys(data).forEach(file => {
      let encounter = data[file];
      if (encounter.new) {
        delete encounter.new;
        encounters.push(encounter);
      }
    });
    r.set('encounters', encounters.sort((a, b) => b.started_at - a.started_at))
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
