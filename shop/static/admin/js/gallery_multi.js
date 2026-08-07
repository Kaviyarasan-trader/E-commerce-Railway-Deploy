/* Enable multiple file selection in the product gallery inline.
   Picking several files at once on one row auto-creates empty rows and
   fills them with the remaining files. Works on initially-rendered rows
   and on rows added later via "Add another". */
(function () {
  'use strict';
  var PREFIX = 'images';

  function bindInputs(scope) {
    var inputs = (scope || document).querySelectorAll('input[type=file]');
    Array.prototype.forEach.call(inputs, function (input) {
      if (input.getAttribute('data-multi-bound')) return;
      input.setAttribute('data-multi-bound', '1');
      input.setAttribute('multiple', 'multiple');
      input.addEventListener('change', function () {
        var files = input.files;
        if (!files || files.length <= 1) return;

        var group = document.getElementById(PREFIX + '-group');
        if (!group) return;
        var addBtn = group.querySelector('a.add-row');

        var extra = files.length - 1;
        for (var i = 0; i < extra; i++) {
          if (addBtn) addBtn.click();
        }

        var all = group.querySelectorAll('input[type=file]');
        var myIndex = Array.prototype.indexOf.call(all, input);
        for (var j = 1; j < files.length; j++) {
          var target = all[myIndex + j];
          if (target && target !== input) {
            var dt = new DataTransfer();
            dt.items.add(files[j]);
            target.files = dt.files;
          }
        }
      });
    });
  }

  function boot() {
    var group = document.getElementById(PREFIX + '-group');
    if (!group) return;
    bindInputs(group);
    if (typeof MutationObserver === 'function') {
      new MutationObserver(function () {
        bindInputs(group);
      }).observe(group, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
