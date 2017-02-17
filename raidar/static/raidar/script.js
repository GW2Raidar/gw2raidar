"use strict";

// XAcquire Django CSRF token for AJAX, and prefix the base URL
(function setupAjaxForAuth() {
  var csrftoken = $('[name="csrfmiddlewaretoken"]').val();

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
  var authData = {
    username: null,
    login: true,
    passwordOK: false,
  };

  var authRactive = new Ractive({
    el: '#container',
    template: '#auth_template',
    data: authData,
    computed: {
      authBad: function authOK() {
        var username = this.get('input.username'),
            password = this.get('input.password'),
            email = this.get('input.email');

        var authOK = username != '' && password != '';
        if (!this.get('login')) {
          var password2 = this.get('input.password2');
          var emailOK = email != ''; // TODO maybe basic pattern check
          var authOK = authOK && password == password2 && emailOK;
        }
        return !authOK;
      },
    }
  });

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
      var username = this.get('input.username'),
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
      var username = this.get('input.username'),
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
})();
