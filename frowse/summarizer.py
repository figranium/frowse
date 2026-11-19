"""Lightweight DOM summarizer for Frowse.

Extracts just enough structural and semantic cues (tags, types, labels,
placeholders, roles, button/link text, and landmark regions) so an AI agent can
craft an exact natural-language query for Folate without receiving a bloated
full DOM or accessibility tree.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

_EXTRACT_SUMMARY_JS = r"""
(sectionSelector) => {
  const root = sectionSelector ? document.querySelector(sectionSelector) : document.body;
  if (!root) {
    return { error: `Section not found: ${sectionSelector}` };
  }

  const isVisible = (el) => {
    if (!el || el.nodeType !== 1) return false;
    if (el.closest('[aria-hidden="true"], [hidden], template')) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
      return false;
    }
    const rects = el.getClientRects();
    return rects.length > 0 && (el.offsetWidth > 0 || el.offsetHeight > 0 || rects[0].width > 0);
  };

  const clean = (s, maxLen = 50) => {
    if (!s) return '';
    const norm = String(s).replace(/\s+/g, ' ').trim();
    if (norm.length <= maxLen) return norm;
    return norm.slice(0, maxLen - 1) + '…';
  };

  const getLabelForInput = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return clean(aria, 45);
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const texts = labelledBy.split(/\s+/).map(id => {
        const ref = document.getElementById(id);
        return ref ? ref.innerText : '';
      }).filter(Boolean).join(' ');
      if (texts.trim()) return clean(texts, 45);
    }
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl && lbl.innerText) return clean(lbl.innerText, 45);
    }
    const parentLabel = el.closest('label');
    if (parentLabel && parentLabel.innerText) return clean(parentLabel.innerText, 45);
    if (el.getAttribute('placeholder')) return clean(el.getAttribute('placeholder'), 45);
    if (el.getAttribute('title')) return clean(el.getAttribute('title'), 45);
    if (el.getAttribute('name')) return clean(el.getAttribute('name'), 45);
    return '';
  };

  const getRegion = (el) => {
    const dialog = el.closest('dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]');
    if (dialog) {
      const lbl = dialog.getAttribute('aria-label') || '';
      return lbl ? `dialog:${clean(lbl, 25)}` : 'dialog';
    }
    const form = el.closest('form');
    if (form) {
      const fName = form.getAttribute('aria-label') || form.getAttribute('name') || form.id || '';
      const navAncestor = form.closest('header, nav');
      const prefix = navAncestor ? `${navAncestor.tagName.toLowerCase()}>form` : 'form';
      return fName ? `${prefix}:${clean(fName, 25)}` : prefix;
    }
    const nav = el.closest('nav, [role="navigation"]');
    if (nav) {
      const lbl = nav.getAttribute('aria-label') || '';
      return lbl ? `nav:${clean(lbl, 25)}` : 'nav';
    }
    const header = el.closest('header, [role="banner"]');
    if (header) return 'header';
    const footer = el.closest('footer, [role="contentinfo"]');
    if (footer) return 'footer';
    const aside = el.closest('aside, [role="complementary"]');
    if (aside) return 'aside';
    const main = el.closest('main, [role="main"]');
    if (main) return 'main';
    return 'body';
  };

  // Headings outline
  const headings = [];
  const seenHeadings = new Set();
  for (const h of root.querySelectorAll('h1, h2, h3')) {
    if (!isVisible(h)) continue;
    const txt = clean(h.innerText, 60);
    if (txt && !seenHeadings.has(txt)) {
      seenHeadings.add(txt);
      headings.push({ level: h.tagName.toLowerCase(), text: txt });
      if (headings.length >= 12) break;
    }
  }

  const interactiveSelector = [
    'a[href]',
    'button',
    'input:not([type="hidden"])',
    'select',
    'textarea',
    '[role="button"]',
    '[role="link"]',
    '[role="menuitem"]',
    '[role="tab"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="combobox"]',
    '[role="textbox"]',
    '[role="searchbox"]',
    '[role="switch"]',
    '[onclick]',
    '[tabindex]:not([tabindex="-1"])',
    '[contenteditable="true"]'
  ].join(', ');

  const counts = { total: 0, links: 0, buttons: 0, inputs: 0, selects: 0, other: 0 };
  const items = [];
  const seenNodes = new Set();

  for (const el of root.querySelectorAll(interactiveSelector)) {
    if (seenNodes.has(el)) continue;
    seenNodes.add(el);
    if (!isVisible(el)) continue;

    const tag = el.tagName.toLowerCase();
    const role = (el.getAttribute('role') || '').toLowerCase();
    const inputType = tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : '';
    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';

    let kind = 'other';
    if (tag === 'input' || tag === 'textarea' || role === 'textbox' || role === 'searchbox' || el.getAttribute('contenteditable') === 'true') {
      if (inputType === 'submit' || inputType === 'button' || inputType === 'reset') {
        kind = 'button';
      } else if (inputType === 'checkbox' || inputType === 'radio' || role === 'checkbox' || role === 'radio' || role === 'switch') {
        kind = 'toggle';
      } else {
        kind = 'input';
      }
    } else if (tag === 'select' || role === 'combobox') {
      kind = 'select';
    } else if (tag === 'button' || role === 'button') {
      kind = 'button';
    } else if (tag === 'a' || role === 'link') {
      kind = 'link';
    } else if (role === 'tab' || role === 'menuitem') {
      kind = role;
    } else if (role === 'checkbox' || role === 'radio' || role === 'switch') {
      kind = 'toggle';
    }

    counts.total += 1;
    if (kind === 'link') counts.links += 1;
    else if (kind === 'button') counts.buttons += 1;
    else if (kind === 'input' || kind === 'toggle') counts.inputs += 1;
    else if (kind === 'select') counts.selects += 1;
    else counts.other += 1;

    let label = '';
    if (kind === 'input' || kind === 'select' || kind === 'toggle') {
      label = getLabelForInput(el);
      if (!label && tag === 'input' && el.value) label = clean(el.value, 35);
    } else {
      label = clean(
        el.innerText ||
        el.getAttribute('aria-label') ||
        el.getAttribute('title') ||
        (el.querySelector('img[alt]') ? el.querySelector('img[alt]').getAttribute('alt') : '') ||
        el.getAttribute('value') ||
        '',
        45
      );
    }

    if (!label && !inputType) continue;

    const item = {
      kind,
      tag,
      type: inputType || undefined,
      role: role || undefined,
      label: label || inputType || tag,
      region: getRegion(el),
      disabled: disabled || undefined,
    };

    if (kind === 'toggle') {
      item.checked = Boolean(el.checked || el.getAttribute('aria-checked') === 'true');
    }

    if (tag === 'input' && inputType !== 'password' && el.value && el.value.length > 0 && kind === 'input') {
      item.value = clean(el.value, 30);
    }

    if (tag === 'select') {
      const opts = Array.from(el.options || []).map(o => clean(o.text, 25)).filter(Boolean);
      item.optionCount = opts.length;
      item.optionsPreview = opts.slice(0, 4);
    }

    items.push(item);
  }

  return {
    title: document.title || '',
    url: window.location.href,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    counts,
    headings,
    items,
  };
}
"""

_EXTRACT_REFS_JS = r"""
(interactiveOnly) => {
  const isVisible = (el) => {
    if (!el || el.nodeType !== 1) return false;
    if (el.closest('[aria-hidden="true"], [hidden], template')) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
      return false;
    }
    const rects = el.getClientRects();
    return rects.length > 0 && (el.offsetWidth > 0 || el.offsetHeight > 0 || rects[0].width > 0);
  };

  const clean = (s, maxLen = 60) => {
    if (!s) return '';
    const norm = String(s).replace(/\s+/g, ' ').trim();
    return norm.length <= maxLen ? norm : norm.slice(0, maxLen - 1) + '…';
  };

  const selector = [
    'a[href]', 'button', 'input:not([type="hidden"])', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="menuitem"]', '[role="tab"]',
    '[role="checkbox"]', '[role="radio"]', '[role="combobox"]', '[role="textbox"]',
    '[role="searchbox"]', '[role="switch"]', '[onclick]', '[tabindex]:not([tabindex="-1"])'
  ].join(', ');

  const getPath = (el) => {
    if (el.id && /^[A-Za-z_][\w-]*$/.test(el.id)) return `#${el.id}`;
    for (const attr of ['data-testid', 'name', 'aria-label', 'placeholder']) {
      const val = el.getAttribute(attr);
      if (val && !val.includes('"') && val.length < 80) {
        return `${el.tagName.toLowerCase()}[${attr}="${val}"]`;
      }
    }
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.body) {
      let idx = 1;
      let sib = cur.previousElementSibling;
      while (sib) {
        if (sib.tagName === cur.tagName) idx++;
        sib = sib.previousElementSibling;
      }
      parts.unshift(`${cur.tagName.toLowerCase()}:nth-of-type(${idx})`);
      cur = cur.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };

  const refs = [];
  let counter = 1;
  for (const el of document.querySelectorAll(selector)) {
    if (!isVisible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || tag;
    const label = clean(
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.innerText ||
      el.getAttribute('title') ||
      el.getAttribute('name') ||
      ''
    );
    refs.push({
      ref: `@e${counter++}`,
      role,
      tag,
      label,
      selector: getPath(el),
    });
  }
  return refs;
}
"""


def _format_item_token(item: dict[str, Any]) -> str:
    kind = item["kind"]
    tag = item["tag"]
    label = item["label"]
    t = item.get("type")

    if kind == "input":
        prefix = f"{tag}[{t}]" if t else tag
        tok = f'{prefix} "{label}"'
        if item.get("value"):
            tok += f' (val="{item["value"]}")'
    elif kind == "toggle":
        prefix = t or item.get("role") or tag
        state = "checked" if item.get("checked") else "unchecked"
        tok = f'{prefix} "{label}" [{state}]'
    elif kind == "select":
        opts = item.get("optionsPreview") or []
        opt_count = item.get("optionCount", 0)
        suffix = ""
        if opts:
            more = f", +{opt_count - len(opts)}" if opt_count > len(opts) else ""
            suffix = f" ({', '.join(opts)}{more})"
        tok = f'select "{label}"{suffix}'
    else:
        tok = f'"{label}"'

    if item.get("disabled"):
        tok += " [disabled]"
    return tok


def format_summary(
    raw: dict[str, Any],
    max_chars: int = 2200,
    max_items_per_group: int = 12,
    pending_dialog: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Format raw extracted DOM data into an ultra-compact Folate-ready summary."""
    counts = raw.get("counts", {})
    headings = raw.get("headings", [])
    items = raw.get("items", [])

    lines: list[str] = []
    title = raw.get("title") or "(untitled)"
    url = raw.get("url") or ""
    lines.append(f"Page: {title} | {url}")

    if pending_dialog:
        lines.append(
            f"Dialog open ({pending_dialog.get('type', 'alert')}): {pending_dialog.get('message', '')}"
        )

    count_parts = []
    for k in ("links", "buttons", "inputs", "selects"):
        v = counts.get(k, 0)
        if v:
            count_parts.append(f"{v} {k}")
    if counts.get("other", 0):
        count_parts.append(f"{counts['other']} other")
    lines.append(
        f"Interactive: {counts.get('total', 0)} ({', '.join(count_parts) if count_parts else 'none'})"
    )

    if headings:
        h_str = " > ".join(f"{h['level']}:{h['text']}" for h in headings[:6])
        if len(headings) > 6:
            h_str += f" (+{len(headings) - 6} more)"
        lines.append(f"Outline: {h_str}")

    # Group items by region -> kind
    regions: OrderedDict[str, dict[str, list[dict[str, Any]]]] = OrderedDict()
    for item in items:
        reg = item.get("region", "body")
        if reg not in regions:
            regions[reg] = {
                "input": [],
                "select": [],
                "toggle": [],
                "button": [],
                "tab": [],
                "menuitem": [],
                "link": [],
                "other": [],
            }
        k = item["kind"]
        regions[reg].setdefault(k, []).append(item)

    region_summaries: list[dict[str, Any]] = []
    for reg_name, groups in regions.items():
        reg_parts: list[str] = []

        # Inputs, selects, toggles are high-signal: keep them crisp and visible
        for k in ("input", "select", "toggle"):
            grp = groups.get(k, [])
            if not grp:
                continue
            dedup: OrderedDict[str, int] = OrderedDict()
            for it in grp:
                tok = _format_item_token(it)
                dedup[tok] = dedup.get(tok, 0) + 1
            formatted = [
                f"{tok} (x{cnt})" if cnt > 1 else tok
                for tok, cnt in list(dedup.items())[:max_items_per_group]
            ]
            if len(dedup) > max_items_per_group:
                formatted.append(f"+{len(dedup) - max_items_per_group} more")
            reg_parts.append(f"{k}s: {', '.join(formatted)}")

        # Buttons, tabs, menu items, links, other: deduplicate repeated labels
        for k, label_name in (
            ("button", "buttons"),
            ("tab", "tabs"),
            ("menuitem", "menu"),
            ("link", "links"),
            ("other", "other"),
        ):
            grp = groups.get(k, [])
            if not grp:
                continue
            dedup: OrderedDict[str, int] = OrderedDict()
            for it in grp:
                tok = _format_item_token(it)
                dedup[tok] = dedup.get(tok, 0) + 1

            limit = max_items_per_group if reg_name.startswith(("nav", "header", "dialog", "form")) else min(8, max_items_per_group)
            shown = [
                f"{tok} (x{cnt})" if cnt > 1 else tok
                for tok, cnt in list(dedup.items())[:limit]
            ]
            hidden_count = sum(list(dedup.values())[limit:])
            if hidden_count > 0:
                shown.append(f"+{hidden_count} more")
            reg_parts.append(f"{label_name} ({len(grp)}): {', '.join(shown)}")

        if reg_parts:
            reg_line = f"[{reg_name}] " + " | ".join(reg_parts)
            region_summaries.append({"region": reg_name, "summary": reg_line})
            lines.append(reg_line)

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 16].rstrip() + "\n... (truncated)"

    return {
        "title": title,
        "url": url,
        "viewport": raw.get("viewport", ""),
        "counts": counts,
        "headings": headings,
        "regions": region_summaries,
        "summary": text,
    }


def summarize_dom(
    target: Any,
    section: str | None = None,
    max_chars: int = 2200,
    max_items_per_group: int = 12,
    pending_dialog: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run DOM extraction on a Playwright Page or Frame and return formatted summary."""
    raw = target.evaluate(_EXTRACT_SUMMARY_JS, section)
    if isinstance(raw, dict) and raw.get("error"):
        raise ValueError(raw["error"])
    return format_summary(
        raw,
        max_chars=max_chars,
        max_items_per_group=max_items_per_group,
        pending_dialog=pending_dialog,
    )


def extract_refs(target: Any, interactive_only: bool = True) -> list[dict[str, str]]:
    """Extract legacy @eN refs for compatibility with `snapshot --refs`."""
    return target.evaluate(_EXTRACT_REFS_JS, interactive_only)
