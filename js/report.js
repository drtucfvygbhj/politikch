/* ============================================================
   "Report a problem" — a short form (type of problem + description) that,
   like the contact form, opens a ready-to-send draft in the visitor's OWN
   email app, addressed to us. The site itself sends and stores nothing: the
   email goes straight from the visitor to our mailbox, and only if they send
   it from there.

   The draft holds what the form shows: the type, the text concerned, the
   description, a link to the page and the site language. Never anything from
   the visitor's own votes (GUARDRAILS PRIV-01). The subject starts with a fixed
   English prefix so arriving mail can be filtered, whatever the language.
   ============================================================ */

let C = null;                       // context from app.js: { t, state, escapeAttr, recipient }
export function configureReport(ctx) { C = ctx; }

const TYPES = ['site', 'data', 'word', 'definition'];
// Fixed English subject per type (stable for inbox filtering).
const SUBJECT = {
  site: 'Problem report — site doesn’t work',
  data: 'Problem report — figure or fact wrong',
  word: 'Problem report — word or translation wrong',
  definition: 'Glossary suggestion',
};
const ORIGIN = 'Problem report';    // the contactRoutes key in data/legal.json
const QUOTE_MAX = 300, MESSAGE_MAX = 1000;
const t = (k) => C.t(k);
function escapeAttr(s) { return C.escapeAttr(s); }

function pageLink() {
  return (location.origin + location.pathname + location.hash).slice(0, 300);
}

export function openReport(opts = {}) {
  const type = TYPES.includes(opts.type) ? opts.type : 'site';
  const quote = String(opts.quote || '').replace(/\s+/g, ' ').trim().slice(0, QUOTE_MAX);
  const trigger = opts.trigger || document.activeElement;
  const link = pageLink();
  document.getElementById('report-modal')?.remove();

  const overlay = document.createElement('div');
  overlay.id = 'report-modal';
  overlay.className = 'contact-overlay';
  overlay.innerHTML = `
    <div class="contact-dialog report-dialog" role="dialog" aria-modal="true" aria-labelledby="report-h">
      <button type="button" class="contact-close" aria-label="${escapeAttr(t('def.close'))}">×</button>
      <h2 id="report-h" class="contact-h">${escapeAttr(t('report.title'))}</h2>
      <fieldset class="report-types">
        <legend class="contact-label">${escapeAttr(t('report.type'))}</legend>
        ${TYPES.map(k => `<label class="report-type"><input type="radio" name="report-type" value="${escapeAttr(k)}"> ${escapeAttr(t('report.type.' + k))}</label>`).join('')}
      </fieldset>
      <label class="contact-label" for="report-quote">${escapeAttr(t('report.quoteLabel'))}</label>
      <textarea id="report-quote" class="contact-textarea" rows="2" maxlength="${escapeAttr(QUOTE_MAX)}"></textarea>
      <label class="contact-label" for="report-message">${escapeAttr(t('report.messageLabel'))}</label>
      <textarea id="report-message" class="contact-textarea" rows="5" maxlength="${escapeAttr(MESSAGE_MAX)}"
                placeholder="${escapeAttr(t('report.messagePlaceholder'))}"></textarea>
      <p class="contact-note">${escapeAttr(t('report.note'))}</p>
      <div class="contact-actions">
        <button type="button" class="contact-cancel">${escapeAttr(t('contact.cancel'))}</button>
        <button type="button" class="contact-send">${escapeAttr(t('contact.send'))}</button>
      </div>
      <p class="contact-fallback" data-fallback></p>
    </div>`;
  document.body.appendChild(overlay);

  const quoteEl = overlay.querySelector('#report-quote');
  const msgEl = overlay.querySelector('#report-message');
  quoteEl.value = quote;
  overlay.querySelectorAll('input[name="report-type"]').forEach(r => { r.checked = r.value === type; });

  const focusables = () => overlay.querySelectorAll('button, input, textarea, a[href]');
  const close = () => {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
    if (trigger && trigger.focus && document.contains(trigger)) trigger.focus();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { close(); return; }
    if (e.key === 'Tab') {                       // simple focus trap
      const f = focusables(); if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  overlay.addEventListener('mousedown', e => { if (e.target === overlay) close(); });
  overlay.querySelector('.contact-close').addEventListener('click', close);
  overlay.querySelector('.contact-cancel').addEventListener('click', close);
  document.addEventListener('keydown', onKey);
  msgEl.addEventListener('input', () => msgEl.classList.remove('contact-invalid'));

  // No email app? The address is shown, as in the contact form.
  C.recipient(ORIGIN).then(email => {
    const fb = overlay.querySelector('[data-fallback]');
    if (email && fb) fb.innerHTML = `${escapeAttr(t('contact.fallback'))} <a href="mailto:${escapeAttr(email)}">${escapeAttr(email)}</a>`;
  });

  overlay.querySelector('.contact-send').addEventListener('click', () => {
    const message = msgEl.value.trim();
    if (!message) { msgEl.classList.add('contact-invalid'); msgEl.focus(); return; }
    const kind = overlay.querySelector('input[name="report-type"]:checked')?.value || 'site';
    const text = quoteEl.value.trim().slice(0, QUOTE_MAX);
    const lines = [
      `${t('report.mail.type')}: ${t('report.type.' + kind)}`,
      `${t('report.mail.page')}: ${link}`,
      `${t('report.mail.lang')}: ${C.state.lang.toUpperCase()}`,
    ];
    if (text) lines.push(`${t('report.mail.quote')}: «${text}»`);
    lines.push('', t('report.messageLabel'), message.slice(0, MESSAGE_MAX));
    C.recipient(ORIGIN).then(email => {
      if (!email) return;
      // A URL, not HTML: opens the visitor's own email app.
      window.location.href = 'mailto:' + email + '?subject=' + encodeURIComponent(SUBJECT[kind])
        + '&body=' + encodeURIComponent(lines.join('\n'));
      close();
    });
  });
  setTimeout(() => (quote ? msgEl : overlay.querySelector('input[name="report-type"]:checked')).focus(), 30);
}
