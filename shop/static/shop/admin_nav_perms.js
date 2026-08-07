(function () {
  function syncNavSection() {
    var staff = document.getElementById('id_is_staff');
    if (!staff) return;
    var on = staff.checked;
    document.querySelectorAll('.admin-nav-section').forEach(function (el) {
      el.style.display = on ? '' : 'none';
    });
    var link = document.querySelector('a[href="#admin-navigation-access-tab"]');
    if (link && link.parentElement) {
      link.parentElement.style.display = on ? '' : 'none';
    }
  }
  document.addEventListener('DOMContentLoaded', function () {
    var staff = document.getElementById('id_is_staff');
    if (staff) { staff.addEventListener('change', syncNavSection); syncNavSection(); }
  });
})();
