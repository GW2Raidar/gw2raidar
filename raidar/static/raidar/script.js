// XAcquire Django CSRF token for AJAX, and prefix the base URL
(function setupAJAX() {
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
})();



// Data Binding
var authData = {
  username: null,
  login: true
};

var authRactive = new Ractive({
  el: '#container',
  template: '#auth_template',
  data: authData
});

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
    }).done(response => {
      this.set('username', username);
    }).fail(response => {
      // TODO fail case
    });
  },
  register: function register() {
    // TODO
  },
  logout: function logout() {
    // TODO
  },
  swap: function swap() {
    this.set({
      login: !this.get('login'),
      'input.password': '',
      'input.password2': '',
    });
  },
});
