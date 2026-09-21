// Generic DOM inspection only. Nodes remain in a JSHandle, never serialized to the model.
({maxElements, maxText}) => {
    const visible = el => {
        if (!(el instanceof Element) || el.closest('[hidden],[aria-hidden="true"],script,style,noscript')) return false;
        const s = getComputedStyle(el), r = el.getBoundingClientRect();
        // Styled checkboxes can use a transparent but full-sized native hit target.
        const styledChoice = el.matches('input[type="checkbox"],input[type="radio"]') &&
            r.width >= 4 && r.height >= 4 && s.pointerEvents !== 'none';
        return s.visibility !== 'hidden' && s.display !== 'none' &&
            (Number(s.opacity) !== 0 || styledChoice) &&
            r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 &&
            r.top < innerHeight && r.left < innerWidth;
    };
    const clean = (s, n=160) => String(s || '').replace(/\s+/g, ' ').trim().slice(0,n);
    const secret = el => el.type === 'password' ||
        /password|one-time-code|cc-number|cc-csc/.test(el.autocomplete || '');
    const name = el => {
        const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/);
        const root = el.getRootNode();
        const labelled = ids.map(id => root.getElementById?.(id)?.textContent || '').join(' ').trim();
        return clean(labelled || el.getAttribute('aria-label') ||
            Array.from(el.labels || []).map(x => x.innerText).join(' ') ||
            (el.tagName === 'INPUT' && ['submit','button','reset'].includes(el.type) ? el.value : '') ||
            el.innerText || el.getAttribute('alt') || el.getAttribute('title') || el.placeholder);
    };
    const role = el => el.getAttribute('role') || ({A:'link', BUTTON:'button',
        TEXTAREA:'textbox', SELECT:'combobox', SUMMARY:'button'})[el.tagName] ||
        (el.tagName === 'INPUT' ? ({checkbox:'checkbox',radio:'radio',submit:'button',
        button:'button',range:'slider',search:'searchbox'})[el.type] || 'textbox' :
        el.isContentEditable ? 'textbox' : '');
    const selector = 'a[href],button,input,textarea,select,summary,[role="button"],'+
        '[role="link"],[role="textbox"],[role="checkbox"],[role="combobox"],'+
        '[role="tab"],[contenteditable="true"],[tabindex]';
    const nodes = [], meta = [], lines = [];
    let length = 0, scanned = 0, truncated = false;
    const visit = root => {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
        let n;
        while ((n = walker.nextNode()) && ++scanned <= 25000) {
            if (n.nodeType === Node.TEXT_NODE && length < maxText && visible(n.parentElement)) {
                if (n.parentElement.closest('textarea,[contenteditable="true"]')) continue;
                const t = clean(n.textContent, Math.min(500, maxText-length));
                if (t) { lines.push(t); length += t.length + 1; }
            }
            if (n.nodeType !== Node.ELEMENT_NODE) continue;
            if (n.matches(selector) && visible(n)) {
                if (nodes.length >= maxElements) { truncated = true; continue; }
                nodes.push(n);
                meta.push({tag:n.tagName.toLowerCase(), role:clean(role(n)), name:name(n),
                    context:clean(n.parentElement?.innerText),
                    text:clean(n.innerText), placeholder:clean(n.placeholder), type:n.type || '',
                    value:secret(n) ? '[redacted]' : clean(n.value,240),
                    checked:!!n.checked || n.getAttribute('aria-checked') === 'true',
                    disabled:!!n.disabled || n.getAttribute('aria-disabled') === 'true',
                    href:clean(n.getAttribute('href'),500),
                    form_role:clean(n.form?.getAttribute('role')),
                    options:n.tagName === 'SELECT' ? Array.from(n.options).slice(0,30).map(o =>
                        ({value:clean(o.value),label:clean(o.label),selected:String(o.selected)})) : []});
            }
            if (n.shadowRoot && visible(n)) visit(n.shadowRoot);
        }
    };
    visit(document.body || document.documentElement);
    return {nodes, meta, text:lines.join('\n').slice(0,maxText),
        truncated:truncated || length >= maxText || scanned > 25000};
}
