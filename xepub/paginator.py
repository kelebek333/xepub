from __future__ import annotations

import json


_SOURCE = r"""
(()=>{
  if (!window.__xepubPaginator) {
    const anchorSelector =
      'h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,table,img,svg';

    window.__xepubPaginator = {
      width() {
        // DOM values are CSS pixels. Device scale and WebKit zoom have
        // already been accounted for here.
        return Math.max(1, document.documentElement.clientWidth || innerWidth);
      },

      direction() {
        return getComputedStyle(document.documentElement).direction === 'rtl' ? -1 : 1;
      },

      normalize() {
        const width = this.width();
        document.querySelectorAll('[data-xepub-extent]').forEach(node => node.remove());
        const raw = Math.max(document.body.scrollWidth,
                             document.documentElement.scrollWidth);
        const pages = Math.max(1, Math.ceil((raw - 0.5) / width));
        const target = pages * width;
        if (target > raw + 0.5) {
          const spacer = document.createElement('i');
          spacer.dataset.xepubExtent = '';
          spacer.setAttribute('aria-hidden', 'true');
          const side = this.direction() < 0 ? 'right' : 'left';
          spacer.style.cssText = `position:absolute;top:0;${side}:${raw}px;` +
            `width:${target - raw}px;height:1px;pointer-events:none`;
          document.body.appendChild(spacer);
        }
        return {width, extent: target, pages};
      },

      metrics(layout = this.normalize()) {
        const index = Math.max(0, Math.min(layout.pages - 1,
          Math.round(Math.abs(scrollX) / layout.width)));
        return {index, pages: layout.pages, width: layout.width,
                extent: layout.extent};
      },

      markStart(width) {
        document.querySelectorAll('[data-xepub-page-start]')
          .forEach(node => node.removeAttribute('data-xepub-page-start'));
        const node = [...document.body.querySelectorAll(anchorSelector)]
          .find(candidate => {
            const rect = candidate.getBoundingClientRect();
            return rect.right > 0 && rect.left < width && rect.bottom > 0;
          });
        if (node) node.dataset.xepubPageStart = '';
      },

      go(index) {
        const layout = this.normalize();
        index = Math.max(0, Math.min(layout.pages - 1, Math.round(index)));
        window.scrollTo({left: index * layout.width * this.direction(),
                         behavior: 'instant'});
        this.markStart(layout.width);
        return this.metrics(layout);
      },

      restoreFraction(fraction) {
        const layout = this.normalize();
        return this.go(Math.round(Math.max(0, Math.min(1, fraction)) *
                                  (layout.pages - 1)));
      },

      restoreAnchor(fraction) {
        const layout = this.normalize();
        const anchor = document.querySelector('[data-xepub-page-start]');
        const index = anchor
          ? Math.floor(Math.abs(anchor.getBoundingClientRect().left + scrollX) /
                       layout.width)
          : Math.round(fraction * (layout.pages - 1));
        return this.go(index);
      },

      snap() {
        const layout = this.normalize();
        return this.go(Math.round(Math.abs(scrollX) / layout.width));
      },

      goTo(selector) {
        const layout = this.normalize();
        const node = document.querySelector(selector);
        if (!node) return this.metrics(layout);
        const index = Math.floor(Math.abs(
          node.getBoundingClientRect().left + scrollX) / layout.width);
        return this.go(index);
      }
    };
  }
  return JSON.stringify(window.__xepubPaginator.__CALL__);
})()
"""


def command(method: str, *arguments) -> str:
    """Return trusted application JavaScript invoking one paginator method."""
    if method not in {"go", "restoreFraction", "restoreAnchor", "snap", "goTo"}:
        raise ValueError(f"Unknown paginator operation: {method}")
    args = ",".join(json.dumps(value) for value in arguments)
    return _SOURCE.replace("__CALL__", f"{method}({args})")
