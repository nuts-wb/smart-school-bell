/* Cadangan: bila CDN Bootstrap gagal dimuat (mis. tanpa internet), modal tetap berfungsi. */
(function () {
  if (window.bootstrap) return;
  document.documentElement.classList.add('no-bs');
  var inst = new WeakMap();
  function Modal(el) { this.el = el; inst.set(el, this); }
  Modal.prototype.show = function () {
    var el = this.el; el.style.display = 'block'; el.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(function () { el.classList.add('show'); });
  };
  Modal.prototype.hide = function () {
    var el = this.el; el.classList.remove('show'); el.style.display = 'none'; el.setAttribute('aria-hidden', 'true');
    el.dispatchEvent(new Event('hidden.bs.modal'));
  };
  Modal.getOrCreateInstance = function (el) { return inst.get(el) || new Modal(el); };
  document.addEventListener('click', function (e) {
    var d = e.target.closest && e.target.closest('[data-bs-dismiss="modal"]');
    if (d) { var m = d.closest('.modal'); if (m) Modal.getOrCreateInstance(m).hide(); }
  });
  document.addEventListener('mousedown', function (e) {
    if (e.target.classList && e.target.classList.contains('modal')) Modal.getOrCreateInstance(e.target).hide();
  });
  window.bootstrap = { Modal: Modal };
})();
