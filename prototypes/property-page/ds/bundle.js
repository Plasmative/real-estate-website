/* @ds-bundle: {"format":4,"namespace":"EstateDS","components":[{"name":"Button"},{"name":"TextField"},{"name":"Badge"},{"name":"FilterChip"},{"name":"LanguageSwitch"},{"name":"PropertyCard"}]} */
(function () {
  var React = window.React;
  var h = React.createElement;
  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) { if (arguments[i]) out.push(arguments[i]); }
    return out.join(' ');
  }
  function omit(obj, keys) {
    var out = {};
    for (var k in obj) { if (Object.prototype.hasOwnProperty.call(obj, k) && keys.indexOf(k) < 0) out[k] = obj[k]; }
    return out;
  }

  function Button(props) {
    var variant = props.variant || 'primary';
    var rest = omit(props, ['variant', 'className', 'href', 'children', 'fullWidth']);
    var className = cx('es-btn', 'es-btn-' + variant, props.fullWidth && 'es-btn-full', props.className);
    if (props.href) return h('a', Object.assign({}, rest, { href: props.href, className: className }), props.children);
    return h('button', Object.assign({ type: 'button' }, rest, { className: className }), props.children);
  }

  var fieldCount = 0;
  function TextField(props) {
    var idRef = React.useRef(null);
    if (idRef.current === null) { fieldCount += 1; idRef.current = props.id || 'es-field-' + fieldCount; }
    var id = idRef.current;
    var helpId = id + '-help', errorId = id + '-error';
    var describedBy = cx(props.help && helpId, props.error && errorId) || undefined;
    var inputProps = omit(props, ['label', 'help', 'error', 'multiline', 'className', 'id']);
    var control = h(props.multiline ? 'textarea' : 'input', Object.assign({}, inputProps, {
      id: id,
      className: cx('es-input', props.multiline && 'es-textarea'),
      'aria-invalid': props.error ? 'true' : undefined,
      'aria-describedby': describedBy
    }));
    return h('div', { className: cx('es-field', props.error && 'es-field-error', props.className) },
      h('label', { className: 'es-field-label', htmlFor: id }, props.label),
      control,
      props.help && !props.error ? h('p', { id: helpId, className: 'es-field-help' }, props.help) : null,
      props.error ? h('p', { id: errorId, className: 'es-field-msg' }, props.error) : null
    );
  }

  function Badge(props) {
    var tone = props.tone || 'neutral';
    return h('span', { className: cx('es-badge', 'es-badge-' + tone, props.className) }, props.children);
  }

  function FilterChip(props) {
    var rest = omit(props, ['selected', 'className', 'children']);
    return h('button', Object.assign({ type: 'button' }, rest, {
      className: cx('es-chip', props.selected && 'es-chip-on', props.className),
      'aria-pressed': props.selected ? 'true' : 'false'
    }), props.children);
  }

  function LanguageSwitch(props) {
    var current = props.current || 'en';
    var langs = props.languages || [
      { code: 'en', label: 'EN', name: 'English', href: '/en/' },
      { code: 'es', label: 'ES', name: 'Español', href: '/es/' }
    ];
    return h('nav', { className: cx('es-lang', props.className), 'aria-label': props.ariaLabel || 'Language' },
      langs.map(function (l) {
        var on = l.code === current;
        return h('a', {
          key: l.code, href: l.href, hrefLang: l.code, lang: l.code,
          className: cx('es-lang-item', on && 'es-lang-on'),
          'aria-current': on ? 'page' : undefined,
          title: l.name
        }, l.label);
      })
    );
  }

  function PropertyCard(props) {
    var facts = (props.facts || []).filter(Boolean).join(' · ');
    var media = props.imageSrc
      ? h('img', { className: 'es-card-img', src: props.imageSrc, alt: props.imageAlt || '', loading: 'lazy' })
      : h('div', { className: 'es-card-img es-card-ph', 'aria-hidden': 'true' }, props.placeholderLabel || 'Photo');
    return h('a', { className: cx('es-card', props.className), href: props.href || '#' },
      h('div', { className: 'es-card-media' },
        media,
        props.status ? h('span', { className: 'es-card-status' }, h(Badge, { tone: props.statusTone || 'neutral' }, props.status)) : null
      ),
      h('div', { className: 'es-card-body' },
        h('h3', { className: 'es-card-name' }, props.name),
        props.location ? h('p', { className: 'es-card-loc' }, props.location) : null,
        facts ? h('p', { className: 'es-card-facts' }, facts) : null,
        props.price ? h('p', { className: 'es-card-price' }, props.price) : null
      )
    );
  }

  var api = { Button: Button, TextField: TextField, Badge: Badge, FilterChip: FilterChip, LanguageSwitch: LanguageSwitch, PropertyCard: PropertyCard };
  window.EstateDS = Object.assign(window.EstateDS || {}, api);
})();
