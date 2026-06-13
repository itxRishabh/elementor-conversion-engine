"""
css_engine.py — Specificity-based CSS Cascade Engine
Handles: selector specificity, media query parsing (numeric breakpoints),
CSS variable resolution, calc() passthrough, external <link> stylesheet fetching.
"""
import re
import os
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# CSS Variable Resolution
# ---------------------------------------------------------------------------
def extract_css_variables(css_content):
    """Extract --custom-prop declarations from :root or body blocks."""
    variables = {}
    root_pattern = re.compile(r'(?::root|body)\s*\{([^}]+)\}', re.IGNORECASE)
    for match in root_pattern.finditer(css_content):
        block = match.group(1)
        for prop in block.split(';'):
            prop = prop.strip()
            if prop.startswith('--'):
                parts = prop.split(':', 1)
                if len(parts) == 2:
                    variables[parts[0].strip()] = parts[1].strip()
    return variables

def resolve_css_variables(value, variables):
    """Replace var(--name, fallback) references with resolved values."""
    if not value or 'var(' not in value:
        return value
    def replacer(m):
        inner = m.group(1).strip()
        parts = inner.split(',', 1)
        var_name = parts[0].strip()
        fallback = parts[1].strip() if len(parts) > 1 else None
        resolved = variables.get(var_name, fallback or '')
        return resolve_css_variables(resolved, variables)
    return re.sub(r'var\(([^)]+)\)', replacer, value)

# ---------------------------------------------------------------------------
# Specificity Calculator
# ---------------------------------------------------------------------------
def calculate_specificity(selector):
    selector = selector.strip()
    if not selector:
        return 0
    # Remove :not() wrapper but keep contents
    selector = re.sub(r':not\(([^)]+)\)', r'\1', selector)
    ids = len(re.findall(r'#[a-zA-Z_][a-zA-Z0-9_-]*', selector))
    classes = len(re.findall(r'\.[a-zA-Z_][a-zA-Z0-9_-]*', selector))
    attrs = len(re.findall(r'\[.*?\]', selector))
    pseudo_classes = len(re.findall(r':(?!:)[a-zA-Z-]+', selector))
    pseudo_elements = len(re.findall(r'::[a-zA-Z-]+', selector))
    clean = re.sub(r'#[a-zA-Z_][a-zA-Z0-9_-]*', '', selector)
    clean = re.sub(r'\.[a-zA-Z_][a-zA-Z0-9_-]*', '', clean)
    clean = re.sub(r'\[.*?\]', '', clean)
    clean = re.sub(r'::?[a-zA-Z-]+', '', clean)
    clean = re.sub(r'[>+~*\s]+', ' ', clean).strip()
    tags = len([t for t in clean.split() if t and re.match(r'^[a-zA-Z]', t)])
    return ids * 100 + (classes + attrs + pseudo_classes) * 10 + (tags + pseudo_elements)

# ---------------------------------------------------------------------------
# Selector Matching (per-compilation cache)
# ---------------------------------------------------------------------------
class SelectorCache:
    """Instance-scoped cache so multiple compilations don't leak state."""
    def __init__(self):
        self._cache = {}

    def get_matches(self, selector, soup):
        if selector not in self._cache:
            try:
                self._cache[selector] = set(soup.select(selector))
            except Exception:
                self._cache[selector] = set()
        return self._cache[selector]

    def matches(self, element, selector, soup):
        return element in self.get_matches(selector, soup)

# ---------------------------------------------------------------------------
# Media Query Breakpoint Detection (numeric, not string-matching)
# ---------------------------------------------------------------------------
def classify_media_query(media_header):
    """Classify a @media header into 'desktop', 'tablet', or 'mobile'."""
    max_match = re.search(r'max-width\s*:\s*(\d+)', media_header)
    min_match = re.search(r'min-width\s*:\s*(\d+)', media_header)

    if max_match:
        px = int(max_match.group(1))
        if px <= 767:
            return 'mobile'
        elif px <= 1024:
            return 'tablet'
        else:
            return 'desktop'
    if min_match:
        px = int(min_match.group(1))
        if px >= 1025:
            return 'desktop'
        elif px >= 768:
            return 'tablet'
        else:
            return 'mobile'
    return 'tablet'

# ---------------------------------------------------------------------------
# CSS Property Parser (handles calc(), important, etc.)
# ---------------------------------------------------------------------------
def parse_properties(properties_str):
    props = {}
    for prop in properties_str.split(';'):
        prop = prop.strip()
        if not prop:
            continue
        parts = prop.split(':', 1)
        if len(parts) == 2:
            name = parts[0].strip().lower()
            val = parts[1].strip().rstrip('!important').strip()
            props[name] = val
    return props

# ---------------------------------------------------------------------------
# Core CSS Cascade Parser
# ---------------------------------------------------------------------------
def parse_css_cascade(css_content, css_variables=None):
    """Parse CSS into a list of (selector, specificity, props, media_type, order)."""
    css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)

    if css_variables is None:
        css_variables = extract_css_variables(css_content)

    rules = []
    order_counter = [0]

    def parse_block(block_str, media_type):
        pattern = re.compile(r'([^{}]+)\{([^}]+)\}', re.MULTILINE)
        for match in pattern.finditer(block_str):
            selectors = match.group(1).strip().split(',')
            props = parse_properties(match.group(2))
            # Resolve CSS variables in values
            for k, v in props.items():
                props[k] = resolve_css_variables(v, css_variables)
            for sel in selectors:
                sel = sel.strip()
                if not sel or sel.startswith('@'):
                    continue
                spec = calculate_specificity(sel)
                rules.append((sel, spec, props.copy(), media_type, order_counter[0]))
                order_counter[0] += 1

    # Walk through the CSS, splitting out @media blocks
    length = len(css_content)
    media_pattern = re.compile(r'@media\s+([^{]*)\{', re.IGNORECASE)
    last_idx = 0

    for match in media_pattern.finditer(css_content):
        start = match.start()
        media_header = match.group(0)
        media_type = classify_media_query(media_header)

        # Parse everything before this @media as desktop
        before = css_content[last_idx:start]
        parse_block(before, 'desktop')

        # Find the matching closing brace
        brace_count = 1
        idx = match.end()
        while idx < length and brace_count > 0:
            if css_content[idx] == '{':
                brace_count += 1
            elif css_content[idx] == '}':
                brace_count -= 1
            idx += 1

        media_body = css_content[match.end():idx - 1]
        parse_block(media_body, media_type)
        last_idx = idx

    if last_idx < length:
        parse_block(css_content[last_idx:], 'desktop')

    return rules, css_variables

# ---------------------------------------------------------------------------
# External Stylesheet Fetcher
# ---------------------------------------------------------------------------
def fetch_external_stylesheets(soup, base_dir=None):
    """Fetch CSS from <link rel='stylesheet'> tags. Returns concatenated CSS string."""
    css_parts = []
    for link in soup.find_all('link', rel='stylesheet'):
        href = link.get('href', '')
        if not href:
            continue
        if href.startswith(('http://', 'https://', '//')):
            url = href if not href.startswith('//') else 'https:' + href
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    css_parts.append(resp.read().decode('utf-8', errors='replace'))
            except Exception as e:
                print(f"  Warning: Could not fetch external CSS {url}: {e}")
        elif base_dir:
            local_path = os.path.join(base_dir, href)
            if os.path.exists(local_path):
                with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
                    css_parts.append(f.read())
            else:
                print(f"  Warning: Local stylesheet not found: {local_path}")
    return '\n'.join(css_parts)

# ---------------------------------------------------------------------------
# Style Resolution for a Single Element
# ---------------------------------------------------------------------------
def resolve_element_styles(element, parsed_rules, soup, cache):
    """Resolve cascaded styles for an element across desktop/tablet/mobile."""
    resolved = {'desktop': {}, 'tablet': {}, 'mobile': {}}

    matching = []
    for selector, spec, props, media_type, order in parsed_rules:
        if cache.matches(element, selector, soup):
            matching.append((spec, order, props, media_type))

    matching.sort(key=lambda x: (x[0], x[1]))

    for _, _, props, media_type in matching:
        if media_type == 'desktop':
            resolved['desktop'].update(props)
        elif media_type == 'tablet':
            resolved['tablet'].update(props)
        elif media_type == 'mobile':
            resolved['mobile'].update(props)

    # Inline styles override everything (specificity 1000)
    inline = element.get('style', '')
    if inline:
        inline_props = parse_properties(inline)
        resolved['desktop'].update(inline_props)

    return resolved

# ---------------------------------------------------------------------------
# Utility: parse inline style string
# ---------------------------------------------------------------------------
def parse_inline_styles(style_str):
    return parse_properties(style_str) if style_str else {}

# ---------------------------------------------------------------------------
# Extract pseudo-element and state rules (::before, ::after, :hover, :focus)
# These can't be mapped to Elementor settings — they go into custom_css
# ---------------------------------------------------------------------------
def extract_pseudo_and_state_rules(css_content, css_variables=None):
    """Extract CSS rules with pseudo-elements/states into a structured dict.
    Returns: list of (base_selector, pseudo_part, properties_dict)
    e.g. ('.card', '::before', {'content': '""', 'position': 'absolute', ...})
    """
    css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
    if css_variables is None:
        css_variables = {}

    pseudo_rules = []
    # Match rules that contain :: or :hover/:focus/:active
    pattern = re.compile(r'([^{}]+)\{([^}]+)\}', re.MULTILINE)

    # Strip out @media blocks first (we process top-level only for custom CSS)
    stripped = re.sub(r'@media[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}', '', css_content, flags=re.DOTALL)

    for match in pattern.finditer(stripped):
        full_selectors = match.group(1).strip()
        props_str = match.group(2).strip()

        for sel in full_selectors.split(','):
            sel = sel.strip()
            # Check for pseudo-elements
            pseudo_match = re.search(r'(::(?:before|after|placeholder|first-line|first-letter|selection))', sel)
            # Check for state pseudo-classes
            state_match = re.search(r'(:(?:hover|focus|active|visited|focus-within|focus-visible))', sel)

            if pseudo_match or state_match:
                if pseudo_match:
                    pseudo_part = pseudo_match.group(1)
                    base_sel = sel[:pseudo_match.start()].strip()
                else:
                    pseudo_part = state_match.group(1)
                    base_sel = sel[:state_match.start()].strip()

                if not base_sel:
                    continue

                props = parse_properties(props_str)
                for k, v in props.items():
                    props[k] = resolve_css_variables(v, css_variables)

                pseudo_rules.append((base_sel, pseudo_part, props))

    return pseudo_rules

def extract_keyframes(css_content):
    """Extract @keyframes blocks from CSS. Returns raw keyframes CSS string."""
    keyframes = []
    kf_pattern = re.compile(r'(@keyframes\s+[a-zA-Z0-9_-]+\s*\{)', re.IGNORECASE)

    for match in kf_pattern.finditer(css_content):
        start = match.start()
        brace_count = 1
        idx = match.end()
        length = len(css_content)
        while idx < length and brace_count > 0:
            if css_content[idx] == '{':
                brace_count += 1
            elif css_content[idx] == '}':
                brace_count -= 1
            idx += 1
        keyframes.append(css_content[start:idx])

    return '\n'.join(keyframes)

def get_element_custom_css(element, pseudo_rules, soup, cache):
    """Build Elementor custom_css string for an element using `selector` keyword.
    Collects matching ::before/::after/hover/focus rules.
    """
    css_parts = []

    for base_sel, pseudo_part, props in pseudo_rules:
        if cache.matches(element, base_sel, soup):
            props_str = '; '.join(f'{k}: {v}' for k, v in props.items())
            css_parts.append(f"selector{pseudo_part} {{ {props_str}; }}")

    return '\n'.join(css_parts)

# Properties that ARE mapped to native Elementor settings (don't put in custom_css)
MAPPED_PROPERTIES = {
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'background', 'background-color', 'background-image', 'background-position',
    'background-size', 'background-repeat',
    'font-size', 'font-family', 'font-weight', 'font-style', 'line-height',
    'letter-spacing', 'text-transform', 'text-align', 'color',
    'width', 'height', 'min-height', 'max-height', 'min-width', 'max-width',
    'display', 'flex-direction', 'flex-wrap', 'justify-content', 'align-items',
    'align-self', 'gap', 'column-gap', 'row-gap', 'flex', 'flex-grow', 'flex-shrink',
    'border', 'border-width', 'border-color', 'border-style', 'border-radius',
    'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width',
    'box-shadow', 'text-shadow', 'opacity', 'overflow', 'overflow-x', 'overflow-y',
    'position', 'top', 'right', 'bottom', 'left', 'z-index',
    'transform', 'grid-template-columns', 'grid-template-rows', 'grid-column',
}

def get_unmapped_inline_css(styles):
    """Return CSS string for properties that have no native Elementor mapping."""
    unmapped = {}
    for k, v in styles.items():
        if k not in MAPPED_PROPERTIES and not k.startswith('--'):
            unmapped[k] = v

    if not unmapped:
        return ""
    props_str = '; '.join(f'{k}: {v}' for k, v in unmapped.items())
    return f"selector {{ {props_str}; }}"
