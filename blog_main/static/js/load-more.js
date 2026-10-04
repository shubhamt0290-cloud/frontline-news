// added by shubham - "Load more" button: replaces the Newer/Older page links with a button that
// fetches the next page and appends its items to the current list (no page reload).
// Without JavaScript the normal pagination links keep working.
(function () {
  'use strict';

  function setup(list) {
    var pagination = list.parentNode.querySelector('.pagination');
    var nextLink = pagination && pagination.querySelector('a.next');
    if (!nextLink) return; // only one page

    var nextUrl = nextLink.href;
    // Hide "Older" + "Page x of y"; keep "Newer" visible if the visitor opened page 2+ directly.
    nextLink.hidden = true;
    var pageLabel = pagination.querySelector('span');
    if (pageLabel) pageLabel.hidden = true;
    if (!pagination.querySelector('a.prev')) pagination.hidden = true;

    var wrap = document.createElement('div');
    wrap.className = 'load-more';
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn';
    button.textContent = 'Load more';
    var status = document.createElement('p');
    status.className = 'mono load-more-status';
    status.setAttribute('aria-live', 'polite');
    wrap.appendChild(button);
    wrap.appendChild(status);
    pagination.parentNode.insertBefore(wrap, pagination);

    button.addEventListener('click', function () {
      button.disabled = true;
      button.textContent = 'Loading…';

      fetch(nextUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
        .then(function (response) {
          if (!response.ok) throw new Error('HTTP ' + response.status);
          return response.text();
        })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, 'text/html');
          var newList = doc.querySelector('[data-list]');
          var items = newList ? Array.prototype.slice.call(newList.children) : [];
          var firstLink = null;

          items.forEach(function (item) {
            var added = document.importNode(item, true);
            list.appendChild(added);
            if (!firstLink) firstLink = added.querySelector('h3 a');
          });
          if (firstLink) firstLink.focus({ preventScroll: true }); // keyboard users continue from the new items

          var next = doc.querySelector('.pagination a.next');
          status.textContent = items.length + ' more loaded.';
          if (next) {
            nextUrl = next.href;
            button.disabled = false;
            button.textContent = 'Load more';
          } else {
            button.remove();
            status.textContent = "You've reached the end.";
          }
        })
        .catch(function () {
          button.disabled = false;
          button.textContent = 'Try again';
          status.textContent = "Couldn't load more stories. Check your connection.";
        });
    });
  }

  document.querySelectorAll('[data-list]').forEach(setup);
})();
