"""widgets.py — Advanced widget detection, semantic section analysis, Pro widget compilation"""
import re
import uuid

def generate_id():
    return uuid.uuid4().hex[:8]

# ---------------------------------------------------------------------------
# Semantic Section Detector
# ---------------------------------------------------------------------------
SECTION_PATTERNS = {
    'hero': {
        'classes': ['hero', 'banner', 'jumbotron', 'masthead', 'hero-section', 'hero-banner'],
        'ids': ['hero', 'banner', 'masthead'],
    },
    'pricing': {
        'classes': ['pricing', 'price-table', 'pricing-table', 'pricing-section', 'plans'],
        'ids': ['pricing', 'plans'],
    },
    'faq': {
        'classes': ['faq', 'faqs', 'accordion', 'faq-section', 'questions'],
        'ids': ['faq', 'faqs'],
    },
    'team': {
        'classes': ['team', 'team-section', 'our-team', 'team-members', 'staff'],
        'ids': ['team', 'our-team'],
    },
    'testimonial': {
        'classes': ['testimonial', 'testimonials', 'reviews', 'client-reviews', 'feedback'],
        'ids': ['testimonials', 'reviews'],
    },
    'cta': {
        'classes': ['cta', 'call-to-action', 'cta-section'],
        'ids': ['cta'],
    },
    'footer': {
        'classes': ['footer', 'site-footer'],
        'ids': ['footer'],
    },
}

def detect_semantic_section(element):
    """Returns semantic section name or None."""
    classes = [c.lower() for c in element.get('class', [])]
    el_id = (element.get('id') or '').lower()
    for section, patterns in SECTION_PATTERNS.items():
        if any(c in classes for c in patterns['classes']):
            return section
        if el_id in patterns['ids']:
            return section
    return None

# ---------------------------------------------------------------------------
# Advanced Widget Detection (fixed: checks DIRECT children, not entire subtree)
# ---------------------------------------------------------------------------
def detect_advanced_widget(element):
    """Detect if element should be compiled as a special widget instead of a container."""
    classes = element.get('class', [])
    lower_classes = [c.lower() for c in classes]
    tag = element.name.lower()
    direct_children = [c for c in element.children if c.name is not None]

    # 1. Carousel / Slider (explicit class-based only)
    slider_classes = ['carousel', 'slider', 'slideshow', 'slick-slider', 'swiper', 'owl-carousel', 'glide']
    if any(c in lower_classes for c in slider_classes):
        return "slides"

    # 2. Form (only if this element IS a form, not if it CONTAINS one deep)
    if tag == 'form':
        return "form"

    # 3. Nav Menu
    if tag == 'nav' or any(c in lower_classes for c in ['navbar', 'navigation', 'nav-menu', 'site-nav']):
        return "nav-menu"

    # 4. Accordion / FAQ (look for toggle patterns)
    accordion_classes = ['accordion', 'faq-list', 'collapse-group']
    if any(c in lower_classes for c in accordion_classes):
        return "accordion"
    # Heuristic: multiple direct children each containing a button/heading + collapsible content
    if len(direct_children) >= 2:
        toggle_count = sum(1 for ch in direct_children
                          if ch.find(['button', 'a'], class_=re.compile(r'collapse|toggle|accordion', re.I))
                          or ch.find(attrs={'data-bs-toggle': 'collapse'}))
        if toggle_count >= 2:
            return "accordion"

    # 5. Tabs
    tab_classes = ['nav-tabs', 'tabs', 'tab-list']
    if any(c in lower_classes for c in tab_classes):
        return "tabs"

    # 6. Counter / Stats (direct children with numbers)
    if len(direct_children) >= 3:
        number_children = 0
        for ch in direct_children:
            text = ch.get_text(strip=True)
            if re.match(r'^[\d,+.%$€£]+$', text):
                number_children += 1
            elif ch.find(text=re.compile(r'^\d{2,}')):
                number_children += 1
        if number_children >= 3 and number_children / len(direct_children) > 0.4:
            return "counter"

    # 7. Progress Bars
    progress_classes = ['progress', 'progress-bar', 'skill-bar']
    if any(c in lower_classes for c in progress_classes):
        return "progress"

    # 8. Icon Box (icon + heading + text pattern in direct children)
    if len(direct_children) >= 2:
        has_icon = any(ch.name == 'i' or ch.find('i') or ch.find('svg') for ch in direct_children[:2])
        has_heading = any(ch.name in ['h1','h2','h3','h4','h5','h6'] for ch in direct_children)
        has_text = any(ch.name == 'p' for ch in direct_children)
        if has_icon and has_heading and has_text and len(direct_children) <= 5:
            return "icon-box"

    # 9. Gallery (STRICT: direct children are mostly images, not deep subtree)
    if tag in ['div', 'section'] and len(direct_children) >= 3:
        img_count = sum(1 for c in direct_children if c.name == 'img' or (c.name in ['div','figure'] and c.find('img', recursive=False)))
        if img_count >= 3 and img_count / len(direct_children) > 0.7:
            return "gallery"

    # 10. Testimonial card (has quote + author pattern)
    testimonial_classes = ['testimonial', 'testimonial-card', 'review-card', 'quote-card']
    if any(c in lower_classes for c in testimonial_classes):
        return "testimonial"

    return None

# ---------------------------------------------------------------------------
# Widget Compilers
# ---------------------------------------------------------------------------
def compile_form_widget(element, css_classes_str=None):
    fields = []
    form_el = element if element.name == 'form' else element.find('form')
    if not form_el: return None

    for inp in form_el.find_all(['input', 'textarea', 'select']):
        in_type = inp.get('type', 'text')
        if in_type in ['hidden', 'submit']: continue
        label_el = form_el.find('label', {'for': inp.get('id')})
        label = label_el.get_text(strip=True) if label_el else inp.get('placeholder', in_type.capitalize())
        fields.append({
            "_id": generate_id()[:5],
            "custom_id": inp.get('name', generate_id()[:5]),
            "field_type": in_type if in_type in ['text','email','textarea','select','checkbox','radio','tel','number','url','date'] else 'text',
            "field_label": label,
            "placeholder": inp.get('placeholder', ''),
            "required": "yes" if inp.has_attr('required') else "",
            "width": "100"
        })

    # Find submit button text
    submit_btn = form_el.find('button', {'type': 'submit'}) or form_el.find('input', {'type': 'submit'})
    submit_text = submit_btn.get_text(strip=True) if submit_btn and submit_btn.name == 'button' else (submit_btn.get('value', 'Submit') if submit_btn else 'Submit')

    settings = {
        "form_fields": fields,
        "form_name": form_el.get('name') or form_el.get('id') or 'Compiled Form',
        "submit_text": submit_text,
    }
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "form",
        "settings": settings, "elements": []
    }

def compile_gallery_widget(element, css_classes_str=None):
    images = []
    for img in element.find_all('img', recursive=True):
        images.append({"url": img.get('src', ''), "id": "", "size": ""})

    settings = {
        "gallery": images,
        "gallery_layout": "grid",
        "columns": min(len(images), 4),
        "gap": {"unit": "px", "size": 10}
    }
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "gallery",
        "settings": settings, "elements": []
    }

def compile_slides_widget(element, css_classes_str=None):
    slides = []
    items = element.find_all(class_=re.compile(r'carousel-item|slide|swiper-slide|glide__slide'))
    if not items:
        items = [c for c in element.children if c.name is not None][:10]

    for item in items:
        img = item.find('img')
        bg_img = img.get('src', '') if img else ""
        h = item.find(['h1','h2','h3','h4','h5'])
        title = h.get_text(strip=True) if h else ""
        p = item.find('p')
        desc = p.get_text(strip=True) if p else ""
        btn = item.find(['a', 'button'])
        btn_text = btn.get_text(strip=True) if btn else ""
        btn_url = btn.get('href', '#') if btn and btn.name == 'a' else "#"

        slides.append({
            "background_image": {"url": bg_img, "id": "", "size": ""},
            "background_color": "#1A1A1A",
            "heading": title,
            "description": desc,
            "button_text": btn_text or "Learn More",
            "link": {"url": btn_url, "is_external": "", "nofollow": "", "custom_attributes": ""}
        })

    settings = {"slides": slides, "slides_height": {"unit": "px", "size": 500}}
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "slides",
        "settings": settings, "elements": []
    }

def compile_accordion_widget(element, css_classes_str=None):
    items = []
    panels = [c for c in element.children if c.name is not None]
    for panel in panels:
        trigger = panel.find(['button', 'a', 'h2', 'h3', 'h4', 'h5'])
        title = trigger.get_text(strip=True) if trigger else "Item"
        # Content is everything except the trigger
        content_parts = []
        for child in panel.children:
            if child == trigger: continue
            if child.name is not None:
                content_parts.append(child.get_text(strip=True))
        content = ' '.join(content_parts) or "Content goes here."
        items.append({
            "_id": generate_id()[:5],
            "tab_title": title,
            "tab_content": content,
        })

    if not items: return None
    settings = {"tabs": items, "selected_icon": {"value": "fas fa-plus", "library": "fa-solid"},
                "selected_active_icon": {"value": "fas fa-minus", "library": "fa-solid"}}
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "accordion",
        "settings": settings, "elements": []
    }

def compile_tabs_widget(element, css_classes_str=None):
    tabs = []
    tab_links = element.find_all(['a', 'button', 'li'])
    for link in tab_links:
        text = link.get_text(strip=True)
        if text:
            tabs.append({"_id": generate_id()[:5], "tab_title": text, "tab_content": f"Content for {text}"})

    if not tabs: return None
    settings = {"tabs": tabs}
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "tabs",
        "settings": settings, "elements": []
    }

def compile_counter_widget(element, css_classes_str=None):
    """Compile a stats/counter section — returns a container with counter widgets."""
    children = [c for c in element.children if c.name is not None]
    counters = []
    for ch in children:
        text = ch.get_text(strip=True)
        num_match = re.search(r'([\d,]+)', text)
        if num_match:
            number = num_match.group(1).replace(',', '')
            label = re.sub(r'[\d,+%$€£]+', '', text).strip() or "Count"
            counters.append({
                "id": generate_id(), "elType": "widget", "widgetType": "counter",
                "settings": {
                    "starting_number": 0, "ending_number": int(number),
                    "title": label, "prefix": "", "suffix": ""
                }, "elements": []
            })

    if not counters: return None
    settings = {"flex_direction": "row", "flex_wrap": "wrap", "content_width": "full",
                "flex_justify_content": "center", "flex_gap": {"unit": "px", "size": 30, "column": "30", "row": "30"}}
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "container", "settings": settings,
        "elements": counters, "isInner": True
    }

def compile_icon_box_widget(element, styles, css_classes_str=None):
    icon_el = element.find('i') or element.find('svg')
    heading_el = element.find(['h1','h2','h3','h4','h5','h6'])
    text_el = element.find('p')

    icon_val = "fas fa-star"
    if icon_el and icon_el.name == 'i':
        ic = icon_el.get('class', [])
        fa = next((c for c in ic if c.startswith('fa-')), None)
        if fa: icon_val = f"fas {fa}"

    settings = {
        "icon": {"value": icon_val, "library": "fa-solid"},
        "title_text": heading_el.get_text(strip=True) if heading_el else "Title",
        "description_text": text_el.get_text(strip=True) if text_el else "",
        "position": "top",
    }
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "icon-box",
        "settings": settings, "elements": []
    }

def compile_testimonial_widget(element, css_classes_str=None):
    img = element.find('img')
    quote = element.find('p') or element.find('blockquote')
    name_el = element.find(['h3','h4','h5','h6','cite','strong'])

    settings = {
        "testimonial_content": quote.get_text(strip=True) if quote else "Great service!",
        "testimonial_name": name_el.get_text(strip=True) if name_el else "Client",
        "testimonial_job": "",
    }
    if img:
        settings["testimonial_image"] = {"url": img.get('src', ''), "id": "", "size": ""}
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "testimonial",
        "settings": settings, "elements": []
    }

def compile_nav_menu_widget(element, css_classes_str=None):
    """Compile nav element into a nav-menu widget instead of silently falling through."""
    menu_items = []
    for link in element.find_all('a'):
        text = link.get_text(strip=True)
        href = link.get('href', '#')
        if text:
            menu_items.append({"text": text, "url": href})

    # Build as HTML widget with the nav markup preserved (Elementor nav-menu
    # requires a registered WP menu, so we use HTML widget as faithful fallback)
    nav_html = '<nav class="compiled-nav"><ul style="list-style:none;display:flex;gap:20px;padding:0;margin:0;">'
    for item in menu_items:
        nav_html += f'<li><a href="{item["url"]}" style="text-decoration:none;">{item["text"]}</a></li>'
    nav_html += '</ul></nav>'

    settings = {"html": nav_html}
    if css_classes_str:
        settings["css_classes"] = css_classes_str

    return {
        "id": generate_id(), "elType": "widget", "widgetType": "html",
        "settings": settings, "elements": []
    }

# ---------------------------------------------------------------------------
# Icon Library Auto-Detection
# ---------------------------------------------------------------------------
def detect_icon_library(classes):
    """Detect icon library from class names. Returns (value, library) tuple."""
    fa_prefixes = {'fa': 'fa-solid', 'fas': 'fa-solid', 'far': 'fa-regular', 'fab': 'fa-brands', 'fal': 'fa-light', 'fad': 'fa-duotone'}
    # FontAwesome
    for prefix, lib in fa_prefixes.items():
        if prefix in classes:
            icon_name = next((c for c in classes if c.startswith('fa-') and c != 'fa-'), None)
            if icon_name:
                return f"{prefix} {icon_name}", lib

    # Material Icons
    if 'material-icons' in classes or 'material-symbols-outlined' in classes:
        return "material-icons", "material"

    # Bootstrap Icons
    bi_icon = next((c for c in classes if c.startswith('bi-')), None)
    if bi_icon:
        return f"bi {bi_icon}", "bootstrap-icons"

    # Iconoir
    iconoir = next((c for c in classes if c.startswith('iconoir-')), None)
    if iconoir:
        return iconoir, "iconoir"

    return None, None
