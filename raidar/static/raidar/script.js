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



  // Data Binding
  let authData = {
    username: window.username,
    login: true,
    passwordOK: false,
  };


  let authRactive = new Ractive({
    el: '#container',
    template: '#auth_template',
    data: authData,
    computed: {
      authBad: function authOK() {
        let username = this.get('input.username'),
            password = this.get('input.password'),
            email = this.get('input.email');

        let authOK = username != '' && password != '';
        if (!this.get('login')) {
          let password2 = this.get('input.password2');
          let emailOK = email != ''; // TODO maybe basic pattern check
          let authOK = authOK && password == password2 && emailOK;
        }
        return !authOK;
      },
    }
  });


  // test for shenanigans
  $.ajax({
    url: 'user',
  }).done(response => {
    authRactive.set('username', response.username);
  }).fail(response => {
    // TODO fail case
  })



  function didLogin(response) {
    if (response.error) {
      // TODO
    } else {
      authRactive.set({
        'input.username': '',
        'input.password': '',
        'input.password2': '',
        username: response.username,
      });
      csrftoken = response.csrftoken;
    }
  }

  authRactive.on({
    login: function login() {
      let username = this.get('input.username'),
          password = this.get('input.password');

      $.post({
        url: 'login',
        data: {
          username: username,
          password: password,
        },
      }).done(didLogin).fail(response => {
        // TODO fail case
      });
    },
    register: function register() {
      let username = this.get('input.username'),
          password = this.get('input.password'),
          email = this.get('input.email');

      $.post({
        url: 'register',
        data: {
          username: username,
          password: password,
          email: email,
        },
      }).done(didLogin).fail(response => {
        // TODO fail case
      });
    },
    logout: function logout() {
      $.post({
        url: 'logout',
      }).done(response => {
        this.set('username', null);
      }).fail(response => {
        // TODO fail case
      })
    },
    swap: function swap() {
      this.set({
        login: !this.get('login'),
        'input.password': '',
        'input.password2': '',
      });
    },
  });

  

  let uploadProgressHandler = (file, evt) => {
    let progress = Math.round(100 * evt.loaded / evt.total);
    console.log(progress, file.name);
    // TODO single upload progress
  }
  let uploadProgressDone = (file, evt) => {
    console.log("DONE", file.name);
    // TODO single upload done
  }

  let makeXHR = file => {
    let req = $.ajaxSettings.xhr();
    req.upload.addEventListener("progress", uploadProgressHandler.bind(null, file), false);
    return req;
  }

  $(document)
    .on('dragstart dragover dragenter', evt => {
      if (authRactive.get('username')) {
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
      if (!authRactive.get('username')) return;

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
        .done(uploadProgressDone.bind(null, file))
        .fail(() => {
          // TODO upload fail case
        });
      });
      $.when(promises).then(results => {
        // TODO all done
      });
      evt.preventDefault();
    });
})();
