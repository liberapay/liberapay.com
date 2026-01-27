document.querySelectorAll('.btn.print').forEach(function (el) {
    el.addEventListener('click', function () { window.print() });
});
document.querySelectorAll('textarea').forEach(function (textarea) {
    if (window.getComputedStyle(textarea)['field-sizing'] == 'content') {
        return;
    }
    var initialHeight = textarea.getBoundingClientRect().height;
    var div = document.createElement('div');
    div.setAttribute('aria-hidden', 'true');
    div.style.whiteSpace = 'pre-wrap';
    div.style.visibility = 'hidden';
    textarea.insertAdjacentElement('afterend', div);
    function update() {
        div.textContent = textarea.value + " ";
        var divHeight = div.getBoundingClientRect().height;
        div.style.marginTop = -divHeight + 'px';
        textarea.style.height = Math.max(divHeight, initialHeight) + 'px';
    }
    textarea.addEventListener('input', update);
    update();
});
