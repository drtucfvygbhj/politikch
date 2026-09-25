/* Applies js/site-settings.js before the page is drawn, so there is no flash of
   the wrong design: picks the design version (1.0 = frozen original, 1.1 = news
   layout) and turns the font and size settings into CSS custom properties that
   css/news.css reads. A classic script (not a module) on purpose — it must run
   synchronously in <head>. */
(function () {
  var FONT_STACKS = {
    playfair: "'Playfair Display', Georgia, serif",
    dmsans: "'DM Sans', system-ui, sans-serif",
    serif: "Charter, 'Iowan Old Style', Georgia, 'Times New Roman', serif",
    sans: "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
  };
  var LIMITS = {
    left: [0.5, 3], centre: [1, 4], right: [0.5, 3], gutter: [8, 40], sectionGap: [8, 80],
    maxWidth: [960, 1800], rule: [1, 4], baseSize: [13, 18],
    mastPad: [4, 60], titleSize: [32, 110], titleScaleX: [70, 140], titleScaleY: [70, 160]
  };
  var DEFAULTS = { left: 1, centre: 2, right: 1, gutter: 26, sectionGap: 32, maxWidth: 1320, rule: 2, baseSize: 15,
    mastPad: 18, titleSize: 58, titleScaleX: 100, titleScaleY: 100 };

  var s = window.PCH_SETTINGS || {};
  var root = document.documentElement;
  root.setAttribute('data-design', s.design === '1.0' ? '1.0' : '1.1');

  var fonts = s.fonts || {};
  root.style.setProperty('--n-serif', FONT_STACKS[fonts.headline] || FONT_STACKS.playfair);
  root.style.setProperty('--n-sans', FONT_STACKS[fonts.body] || FONT_STACKS.dmsans);

  var layout = s.layout || {};
  Object.keys(DEFAULTS).forEach(function (k) {
    var v = Number(layout[k]);
    if (!isFinite(v) || v < LIMITS[k][0] || v > LIMITS[k][1]) v = DEFAULTS[k];
    if (k === 'titleScaleX') { root.style.setProperty('--n-titleSX', v / 100); return; }
    if (k === 'titleScaleY') { root.style.setProperty('--n-titleSY', v / 100); return; }
    var unit = (k === 'left' || k === 'centre' || k === 'right') ? '' : 'px';
    root.style.setProperty('--n-' + k, v + unit);
  });
})();
