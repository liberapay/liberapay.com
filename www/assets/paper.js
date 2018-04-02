document.querySelectorAll('.btn.print').forEach(function (el) {
    el.addEventListener('click', function () { window.print() });
});
