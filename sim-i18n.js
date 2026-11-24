/* Shared language switcher for the 3D simulators (EN / 한국어 / বাংলা).
   A simulator defines, BEFORE loading this file:
     window.SIM_I18N = {
       dict: { 'English text': ['Korean', 'Bangla'], ... },          // exact text (spaces collapsed)
       patterns: [ [/^Floor (\d+)$/, '$1층', '$1 তলা'], ... ],      // for text built at runtime; $1.. = captures
       barStyle: 'top:10px;right:10px'                                 // optional: where the language pill sits
     };
   Every text node, title, placeholder and aria-label is translated, and text the simulator changes later
   (status lines, alarms, counters) is translated as it appears. Canvas text can use window.simT('text'),
   and redraw on the 'simlangchange' event. The choice is shared with the portfolio page (same localStorage key). */
(function () {
  var CFG = window.SIM_I18N || {}, D = CFG.dict || {}, P = CFG.patterns || [];
  var COL = { ko: 0, bn: 1 }, LANGS = ['en', 'ko', 'bn'], KEY = 'portfolio-lang';
  var lang = 'en', busy = false;
  var norm = function (s) { return s.replace(/\s+/g, ' ').trim(); };

  function tr(s, l) {
    l = l || lang;
    if (l === 'en' || s == null) return s;
    var m = String(s).match(/^(\s*)([\s\S]*?)(\s*)$/), core = norm(m[2]);
    if (!core) return s;
    var hit = D[core];
    if (hit && hit[COL[l]]) return m[1] + hit[COL[l]] + m[3];
    for (var i = 0; i < P.length; i++) {
      var p = P[i], r = core.match(p[0]);
      if (!r) continue;
      var out = p[COL[l] + 1];
      if (typeof out === 'function') out = out.apply(null, r);
      else if (out != null) out = out.replace(/\$(\d)/g, function (_, n) { var g = r[+n] || ''; return (D[g] && D[g][COL[l]]) || g; });
      if (out != null) return m[1] + out + m[3];
    }
    return s;
  }
  window.simT = function (s) { return tr(s); };
  window.simLang = function () { return lang; };

  // ---- text nodes: remember the English source so switching back is exact ----
  var src = new WeakMap(); // node -> { en, out }
  function doText(n) {
    var p = n.parentNode && n.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') return;
    if (n.parentNode && n.parentNode.closest && n.parentNode.closest('[data-noi18n]')) return;
    var rec = src.get(n), v = n.nodeValue;
    if (!rec || v !== rec.out) { rec = { en: v }; src.set(n, rec); }   // new or rewritten by the simulator
    var t = tr(rec.en);
    rec.out = t;
    if (v !== t) n.nodeValue = t;
  }
  var ATTRS = ['title', 'placeholder', 'aria-label'];
  var asrc = new WeakMap(); // element -> { attr: {en, out} }
  function doAttrs(el) {
    if (!el.getAttribute) return;
    if (el.closest && el.closest('[data-noi18n]')) return;
    var rec = asrc.get(el) || {};
    ATTRS.forEach(function (a) {
      if (!el.hasAttribute(a)) return;
      var v = el.getAttribute(a), r = rec[a];
      if (!r || v !== r.out) r = rec[a] = { en: v };
      r.out = tr(r.en);
      if (v !== r.out) el.setAttribute(a, r.out);
    });
    asrc.set(el, rec);
  }
  function walk(root) {
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9) return;
    if (root.nodeType === 1) doAttrs(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (var n; (n = w.nextNode());) { if (n.nodeType === 3) doText(n); else doAttrs(n); }
  }

  var mo = new MutationObserver(function (list) {
    if (busy) return;
    busy = true;
    try {
      list.forEach(function (m) {
        if (m.type === 'characterData') doText(m.target);
        else if (m.type === 'attributes') doAttrs(m.target);
        else m.addedNodes.forEach(walk);
      });
    } finally { busy = false; }
  });

  // ---- the language pill ----
  var bar;
  function buildBar() {
    bar = document.createElement('div');
    bar.setAttribute('data-noi18n', '');
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', 'Language');
    bar.style.cssText = 'position:fixed;z-index:9999;display:flex;gap:2px;padding:3px;border-radius:999px;' +
      'background:rgba(20,26,33,.82);border:1px solid rgba(255,255,255,.18);font:500 12px/1 system-ui,"Malgun Gothic","Nirmala UI",sans-serif;' +
      'backdrop-filter:blur(4px);' + (CFG.barStyle || 'top:10px;right:10px');
    [['en', 'EN'], ['ko', '한국어'], ['bn', 'বাংলা']].forEach(function (x) {
      var b = document.createElement('button');
      b.type = 'button'; b.textContent = x[1]; b.dataset.lang = x[0]; b.lang = x[0];
      b.style.cssText = 'border:0;border-radius:999px;padding:5px 9px;cursor:pointer;font:inherit;background:transparent;color:#e6eaee';
      b.addEventListener('click', function () { setLang(x[0], true); });
      bar.appendChild(b);
    });
    document.body.appendChild(bar);
  }
  function paintBar() {
    if (!bar) return;
    [].forEach.call(bar.children, function (b) {
      var on = b.dataset.lang === lang;
      b.setAttribute('aria-pressed', String(on));
      b.style.background = on ? '#f0a020' : 'transparent';
      b.style.color = on ? '#18212b' : '#e6eaee';
    });
  }

  var enTitle = document.title;
  function setLang(l, save) {
    if (LANGS.indexOf(l) < 0) l = 'en';
    if (l === lang && document.documentElement.getAttribute('data-sim-lang')) return;
    lang = l;
    busy = true;
    try { walk(document.body); } finally { busy = false; }
    document.title = tr(enTitle);
    document.documentElement.lang = l;
    document.documentElement.setAttribute('data-sim-lang', l);
    paintBar();
    if (save) {
      try { localStorage.setItem(KEY, l); } catch (e) {}
      try { var u = new URL(location.href); if (l === 'en') u.searchParams.delete('lang'); else u.searchParams.set('lang', l); history.replaceState(null, '', u); } catch (e) {}
      try { if (window.parent !== window) window.parent.postMessage({ type: 'portfolio-lang', lang: l }, location.origin); } catch (e) {}
    }
    try { window.dispatchEvent(new CustomEvent('simlangchange', { detail: { lang: l } })); } catch (e) {}
  }
  window.simSetLang = setLang;

  function start() {
    var st = document.createElement('style');
    st.textContent = 'html[lang="ko"] body{word-break:keep-all}';
    document.head.appendChild(st);
    var l = null;
    try { l = new URL(location.href).searchParams.get('lang'); } catch (e) {}
    if (!l) { try { l = localStorage.getItem(KEY); } catch (e) {} }
    if (!l) { var nl = (navigator.language || '').slice(0, 2); l = nl === 'ko' || nl === 'bn' ? nl : 'en'; }
    buildBar();
    setLang(l, false);
    mo.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    // follow the portfolio page (when embedded) and other tabs
    window.addEventListener('message', function (e) {
      if (e.origin === location.origin && e.data && e.data.type === 'portfolio-lang') setLang(e.data.lang, false);
    });
    window.addEventListener('storage', function (e) { if (e.key === KEY && e.newValue) setLang(e.newValue, false); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
