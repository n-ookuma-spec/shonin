/**
 * envConfig.js
 * window.location.hostname でステージング/本番 Firebase Config を自動切替
 *
 * staging : localhost / 127.0.0.1 / hostname に "staging" を含む場合
 * production : それ以外
 */
(function () {
  var CONFIGS = {
    staging: {
      apiKey:            "AIzaSyBOsg5aFtv8BDV0LS5s6ZakOmrVnxfh0SQ",
      authDomain:        "shonin-staging-89db3.firebaseapp.com",
      projectId:         "shonin-staging-89db3",
      storageBucket:     "shonin-staging-89db3.firebasestorage.app",
      messagingSenderId: "600079760283",
      appId:             "1:600079760283:web:318604ab2579a35e147f3e"
    },
    production: {
      apiKey:            "AIzaSyD55YvLrYlYpSfXS-wnBdI2Pk3ExXVzzgE",
      authDomain:        "shonin-prod.firebaseapp.com",
      projectId:         "shonin-prod",
      storageBucket:     "shonin-prod.firebasestorage.app",
      messagingSenderId: "735996618911",
      appId:             "1:735996618911:web:73f59560d79c80b9d65aaa"
    }
  };

  var h = window.location.hostname;
  var isStaging = h === 'localhost' || h === '127.0.0.1' || h.indexOf('staging') !== -1;

  window.FIREBASE_CONFIG = isStaging ? CONFIGS.staging : CONFIGS.production;
  window.APP_ENV = isStaging ? 'staging' : 'production';
})();
