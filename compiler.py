"""
compiler.py — Best-in-Market HTML to Elementor JSON Template Compiler
Architecture: Modular (css_engine, tw_bs, widgets)

Fixes applied:
  - Instance-scoped SelectorCache (no module-global leak)
  - Numeric media query breakpoint detection (not string matching)
  - CSS variable (--custom-prop) resolution
  - calc() passthrough
  - External <link rel="stylesheet"> fetching
  - Full Tailwind JIT arbitrary value parsing
  - Proper isInner propagation on nested containers
  - _element_id on every element for custom CSS targeting
  - Fixed gallery detection (direct children, not deep subtree)
  - Accordion, tabs, testimonial, counter, icon-box, nav-menu widget detection
  - Multi-library icon detection (FA, Material, Bootstrap Icons)
  - Semantic section labeling (hero, pricing, FAQ, team, etc.)
"""
import os, json, uuid, re, sys, argparse, base64
import urllib.request, urllib.error, mimetypes
from bs4 import BeautifulSoup

from css_engine import (
    SelectorCache, parse_css_cascade, fetch_external_stylesheets,
    resolve_element_styles, extract_css_variables, parse_inline_styles,
    extract_pseudo_and_state_rules, get_element_custom_css, get_unmapped_inline_css,
    extract_keyframes
)
from tw_bs import translate_tailwind_class, translate_bootstrap_class
from widgets import (
    detect_advanced_widget, detect_semantic_section, detect_icon_library,
    compile_form_widget, compile_gallery_widget, compile_slides_widget,
    compile_accordion_widget, compile_tabs_widget, compile_counter_widget,
    compile_icon_box_widget, compile_testimonial_widget, compile_nav_menu_widget,
    generate_id
)

# ---------------------------------------------------------------------------
# Elementor Helper: dimension parsing
# ---------------------------------------------------------------------------
def parse_shorthand_dimension(value):
    if not value: return None
    parts = re.sub(r'\s+', ' ', value.strip()).split(' ')
    if len(parts) == 1:   t = r = b = l = parts[0]
    elif len(parts) == 2: t = b = parts[0]; r = l = parts[1]
    elif len(parts) == 3: t = parts[0]; r = l = parts[1]; b = parts[2]
    else:                 t, r, b, l = parts[:4]

    def exuv(v):
        m = re.match(r'(-?\d+(?:\.\d+)?)(px|%|em|rem|vh|vw|pt)?', v)
        return (m.group(2) or 'px', m.group(1)) if m else ('px', '0')

    tu, tv = exuv(t); _, rv = exuv(r); _, bv = exuv(b); _, lv = exuv(l)
    return {"unit": tu, "top": tv, "right": rv, "bottom": bv, "left": lv, "isLinked": tv == rv == bv == lv}

def get_padding_or_margin(styles, prefix='padding'):
    res = {"unit":"px","top":"0","right":"0","bottom":"0","left":"0","isLinked":True}
    sh = styles.get(prefix)
    if sh:
        p = parse_shorthand_dimension(sh)
        if p: res.update(p)
    for side in ['top','right','bottom','left']:
        v = styles.get(f"{prefix}-{side}")
        if v:
            m = re.match(r'(-?\d+(?:\.\d+)?)(px|%|em|rem|vh|vw|pt)?', v)
            if m: res[side] = m.group(1); res["unit"] = m.group(2) or "px"
    res["isLinked"] = res["top"] == res["right"] == res["bottom"] == res["left"]
    return res

def has_nonzero(dim):
    return dim["top"] != "0" or dim["right"] != "0" or dim["bottom"] != "0" or dim["left"] != "0"

def get_bootstrap_width(classes):
    w = wt = wm = None
    for cls in classes:
        if not cls.startswith('col-'): continue
        parts = cls.split('-')
        if len(parts) == 2:
            try: w = {"unit":"%","size":round(int(parts[1])/12*100,2)}
            except ValueError: pass
        elif len(parts) == 3:
            try:
                pct = round(int(parts[2])/12*100,2)
                bp = parts[1]
                if bp in ['lg','xl','xxl']: w = {"unit":"%","size":pct}
                elif bp == 'md': wt = {"unit":"%","size":pct}
                elif bp == 'sm': wm = {"unit":"%","size":pct}
            except ValueError: pass
    return w, wt, wm

def get_color(styles, key):
    v = styles.get(key)
    return v.strip() if v else None

def get_background(styles):
    bg = {}
    bgi = styles.get('background-image')
    bgc = styles.get('background-color')
    # Gradient detection (linear-gradient, radial-gradient)
    gradient_val = None
    for key in ['background-image', 'background']:
        val = styles.get(key, '')
        gm = re.search(r'((?:linear|radial|conic)-gradient\(.*?\))(?:\s|$|,)', val)
        if gm:
            gradient_val = gm.group(1)
            break
    if gradient_val:
        bg.update({"background_background":"gradient",
                   "background_color":"transparent",
                   "background_color_b":"transparent",
                   "__globals__":{},
                   "background_gradient_type":"linear" if 'linear' in gradient_val else "radial"})
        # Try to extract angle
        angle_m = re.search(r'(\d+)deg', gradient_val)
        if angle_m:
            bg["background_gradient_angle"] = {"unit":"deg","size":int(angle_m.group(1))}
        # Extract color stops
        colors = re.findall(r'(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\))', gradient_val)
        if len(colors) >= 1: bg["background_color"] = colors[0]
        if len(colors) >= 2: bg["background_color_b"] = colors[1]
        return bg
    if bgi:
        m = re.search(r'url\([\'"]?(.*?)[\'"]?\)', bgi)
        if m:
            bg.update({"background_background":"classic",
                       "background_image":{"url":m.group(1),"id":"","size":""},
                       "background_position":"center center","background_size":"cover","background_repeat":"no-repeat"})
    elif bgc:
        bg.update({"background_background":"classic","background_color":bgc})
    bgs = styles.get('background')
    if bgs and not bg:
        um = re.search(r'url\([\'"]?(.*?)[\'"]?\)', bgs)
        if um:
            bg.update({"background_background":"classic",
                       "background_image":{"url":um.group(1),"id":"","size":""},
                       "background_position":"center center","background_size":"cover","background_repeat":"no-repeat"})
        cm = re.search(r'(#[0-9a-fA-F]{3,8}|rgba?\(.*?\))', bgs)
        if cm and not um:
            bg.update({"background_background":"classic","background_color":cm.group(1)})
    return bg

def get_typography(styles):
    t = {}
    fs = styles.get('font-size')
    if fs:
        m = re.match(r'(\d+(?:\.\d+)?)(px|%|em|rem|vh|vw|pt)?', fs)
        if m: t["typography_font_size"] = {"unit":m.group(2) or "px","size":float(m.group(1))}
    ff = styles.get('font-family')
    if ff: t["typography_font_family"] = ff.split(',')[0].strip(' \'"')
    fw = styles.get('font-weight')
    if fw: t["typography_font_weight"] = fw.strip()
    lh = styles.get('line-height')
    if lh:
        m = re.match(r'(\d+(?:\.\d+)?)(px|%|em|rem)?', lh)
        if m: t["typography_line_height"] = {"unit":m.group(2) or "em","size":float(m.group(1))}
    ls = styles.get('letter-spacing')
    if ls:
        m = re.match(r'(-?\d+(?:\.\d+)?)(px|em)?', ls)
        if m: t["typography_letter_spacing"] = {"unit":m.group(2) or "px","size":float(m.group(1))}
    tt = styles.get('text-transform')
    if tt: t["typography_text_transform"] = tt.strip()
    if t: t["typography_typography"] = "custom"
    return t

def get_flex_settings(styles):
    f = {}
    disp = styles.get('display')
    fd = styles.get('flex-direction'); fw = styles.get('flex-wrap')
    jc = styles.get('justify-content'); ai = styles.get('align-items'); g = styles.get('gap')
    # CSS Grid → Flex conversion: grid with columns becomes flex row wrap
    if disp == 'grid':
        gtc = styles.get('grid-template-columns', '')
        col_match = re.search(r'repeat\((\d+)', gtc)
        cols = int(col_match.group(1)) if col_match else gtc.count('fr') + gtc.count('px') + gtc.count('%')
        if cols < 1: cols = 1
        f["flex_direction"] = "row"
        f["flex_wrap"] = "wrap"
        f["_grid_columns"] = cols  # used by children for width calc
        if jc:
            v = jc.strip()
            if v == 'start': v = 'flex-start'
            if v == 'end': v = 'flex-end'
            f["flex_justify_content"] = v
        if ai:
            v = ai.strip()
            if v == 'start': v = 'flex-start'
            if v == 'end': v = 'flex-end'
            f["flex_align_items"] = v
        if g:
            m = re.match(r'(\d+(?:\.\d+)?)(px|%|em|rem)?', g)
            if m: f["flex_gap"] = {"unit":m.group(2) or 'px',"size":float(m.group(1)),"column":m.group(1),"row":m.group(1)}
    elif disp == 'flex' or fd or fw or jc or ai:
        f["flex_direction"] = fd or "column"
        f["flex_wrap"] = fw or "nowrap"
        if jc:
            v = jc.strip()
            if v == 'start': v = 'flex-start'
            if v == 'end': v = 'flex-end'
            f["flex_justify_content"] = v
        if ai:
            v = ai.strip()
            if v == 'start': v = 'flex-start'
            if v == 'end': v = 'flex-end'
            f["flex_align_items"] = v
        if g:
            m = re.match(r'(\d+(?:\.\d+)?)(px|%|em|rem)?', g)
            if m: f["flex_gap"] = {"unit":m.group(2) or 'px',"size":float(m.group(1)),"column":m.group(1),"row":m.group(1)}
    return f

# ---------------------------------------------------------------------------
# Resolve styles with Tailwind/Bootstrap utility injection
# ---------------------------------------------------------------------------
def resolve_full_styles(element, parsed_rules, soup, cache):
    """CSS cascade + utility classes + inline styles."""
    resolved = resolve_element_styles(element, parsed_rules, soup, cache)
    classes = element.get('class', [])

    for cls in classes:
        media = 'desktop'; actual = cls
        if ':' in cls:
            prefix, actual = cls.split(':', 1)
            bp_map = {'sm':'mobile','md':'tablet','lg':'desktop','xl':'desktop','2xl':'desktop',
                       'xs':'mobile','mobile':'mobile','tablet':'tablet'}
            media = bp_map.get(prefix, 'desktop')

        tw = translate_tailwind_class(actual)
        bs = translate_bootstrap_class(actual)
        combined = {**tw, **bs}
        if combined:
            if media == 'desktop':
                resolved['desktop'].update(combined)
            else:
                resolved[media].update(combined)

    return resolved

# ---------------------------------------------------------------------------
# Apply responsive overrides helper
# ---------------------------------------------------------------------------
def apply_responsive_flex(settings, tab_styles, mob_styles):
    for suffix, styles in [('_tablet', tab_styles), ('_mobile', mob_styles)]:
        fl = get_flex_settings(styles)
        for k in ['flex_direction','flex_wrap','flex_justify_content','flex_align_items','flex_gap']:
            if k in fl: settings[k + suffix] = fl[k]
        pad = get_padding_or_margin(styles, 'padding')
        if has_nonzero(pad): settings["padding" + suffix] = pad
        mar = get_padding_or_margin(styles, 'margin')
        if has_nonzero(mar): settings["margin" + suffix] = mar

# ---------------------------------------------------------------------------
# Core Element Compiler
# ---------------------------------------------------------------------------
def compile_element(element, css_rules, pseudo_rules, soup, cache, depth=0):
    if element.name is None: return None

    classes = element.get('class', [])
    css_id = element.get('id')
    css_classes_str = ' '.join(classes) if classes else None
    tag = element.name.lower()

    # Resolve styles
    resolved = resolve_full_styles(element, css_rules, soup, cache)
    styles = resolved['desktop']
    tab_styles = resolved['tablet']
    mob_styles = resolved['mobile']

    # Custom CSS fallback for pseudo-elements, hover/focus, and unmapped styles
    custom_css_parts = []
    p_css = get_element_custom_css(element, pseudo_rules, soup, cache)
    if p_css: custom_css_parts.append(p_css)
    un_css = get_unmapped_inline_css(styles)
    if un_css: custom_css_parts.append(un_css)
    custom_css_val = "\n".join(custom_css_parts) if custom_css_parts else None

    # Check for advanced widget BEFORE container/widget decision
    adv = detect_advanced_widget(element)
    if adv:
        if adv == "form": return compile_form_widget(element, css_classes_str)
        if adv == "gallery": return compile_gallery_widget(element, css_classes_str)
        if adv == "slides": return compile_slides_widget(element, css_classes_str)
        if adv == "accordion": return compile_accordion_widget(element, css_classes_str)
        if adv == "tabs": return compile_tabs_widget(element, css_classes_str)
        if adv == "counter": return compile_counter_widget(element, css_classes_str)
        if adv == "icon-box": return compile_icon_box_widget(element, styles, css_classes_str)
        if adv == "testimonial": return compile_testimonial_widget(element, css_classes_str)
        if adv == "nav-menu": return compile_nav_menu_widget(element, css_classes_str)

    # Container vs Widget
    direct_children = [c for c in element.children if c.name is not None]
    is_container = tag in ['div','section','article','aside','header','footer','nav','main','figure']
    if len(direct_children) > 0 and tag not in ['button','a','select','h1','h2','h3','h4','h5','h6','p','li','ul','ol']:
        is_container = True

    if is_container:
        s = {"flex_direction":"column","flex_wrap":"nowrap","content_width":"full",
             "_element_id": generate_id()}
        if css_classes_str: s["css_classes"] = css_classes_str; s["_css_classes"] = css_classes_str
        if css_id: s["css_id"] = css_id; s["_css_id"] = css_id

        # Semantic label
        sem = detect_semantic_section(element)
        if sem: s["_title"] = sem.replace('-', ' ').title()

        s.update(get_flex_settings(styles))
        s["padding"] = get_padding_or_margin(styles, 'padding')
        s["margin"] = get_padding_or_margin(styles, 'margin')

        # Responsive overrides
        apply_responsive_flex(s, tab_styles, mob_styles)

        # Width
        for suffix, st in [('', styles), ('_tablet', tab_styles), ('_mobile', mob_styles)]:
            wv = st.get('width')
            if wv:
                m = re.match(r'(\d+(?:\.\d+)?)(px|%)', wv)
                if m:
                    s["width" + suffix] = {"unit":m.group(2),"size":float(m.group(1))}
                    if not suffix and m.group(2) == '%' and float(m.group(1)) < 100:
                        s["content_width"] = "boxed"

        bw, bwt, bwm = get_bootstrap_width(classes)
        if bw and "width" not in s: s["width"] = bw; s["_flex_size"] = "none"; s["_element_width"] = "initial"
        if bwt and "width_tablet" not in s: s["width_tablet"] = bwt
        if bwm and "width_mobile" not in s: s["width_mobile"] = bwm

        s.update(get_background(styles))

        # Border
        brd = styles.get('border')
        if brd:
            s["border_border"] = "solid"
            mw = re.search(r'(\d+)px', brd)
            if mw:
                w = mw.group(1)
                s["border_width"] = {"unit":"px","top":w,"right":w,"bottom":w,"left":w,"isLinked":True}
            mc = re.search(r'(#[0-9a-fA-F]{3,8}|rgba?\(.*?\))', brd)
            if mc: s["border_color"] = mc.group(1)
        br = styles.get('border-radius')
        if br:
            m = re.match(r'(\d+(?:\.\d+)?)(px|%|rem)?', br)
            if m:
                r = m.group(1)
                s["border_radius"] = {"unit":m.group(2) or "px","top":r,"right":r,"bottom":r,"left":r,"isLinked":True}

        # Box shadow — parse actual values
        bsv = styles.get('box-shadow')
        if bsv and bsv != 'none':
            s["box_shadow_box_shadow_type"] = "yes"
            bs_nums = re.findall(r'(-?\d+(?:\.\d+)?)px', bsv)
            bs_color = re.search(r'(rgba?\([^)]+\)|#[0-9a-fA-F]{3,8})', bsv)
            s["box_shadow_box_shadow"] = {
                "horizontal": float(bs_nums[0]) if len(bs_nums) > 0 else 0,
                "vertical": float(bs_nums[1]) if len(bs_nums) > 1 else 4,
                "blur": float(bs_nums[2]) if len(bs_nums) > 2 else 10,
                "spread": float(bs_nums[3]) if len(bs_nums) > 3 else 0,
                "color": bs_color.group(1) if bs_color else "rgba(0,0,0,0.15)"
            }

        # Text shadow
        tsv = styles.get('text-shadow')
        if tsv and tsv != 'none':
            s["text_shadow_text_shadow_type"] = "yes"
            ts_nums = re.findall(r'(-?\d+(?:\.\d+)?)px', tsv)
            ts_color = re.search(r'(rgba?\([^)]+\)|#[0-9a-fA-F]{3,8})', tsv)
            s["text_shadow_text_shadow"] = {
                "horizontal": float(ts_nums[0]) if len(ts_nums) > 0 else 0,
                "vertical": float(ts_nums[1]) if len(ts_nums) > 1 else 2,
                "blur": float(ts_nums[2]) if len(ts_nums) > 2 else 4,
                "color": ts_color.group(1) if ts_color else "rgba(0,0,0,0.3)"
            }

        # Overflow (all values)
        ov = styles.get('overflow')
        if ov in ['hidden', 'auto', 'scroll']: s["overflow"] = ov

        # Opacity
        op = styles.get('opacity')
        if op:
            try:
                opv = float(op)
                if opv < 1: s["_opacity"] = {"unit":"","size":opv * 100}  # Elementor uses 0-100
            except ValueError: pass

        # Display none → hide element
        disp = styles.get('display')
        if disp == 'none':
            s["_element_width"] = "auto"
            s["_hidden"] = True  # custom flag — Elementor uses responsive hide
            s["hide_desktop"] = "hidden"
            s["hide_tablet"] = "hidden"
            s["hide_mobile"] = "hidden"

        # Position (absolute, fixed, sticky)
        pos = styles.get('position')
        if pos in ['absolute', 'fixed', 'sticky']:
            s["position"] = pos
            # Map top/left/right/bottom
            for side in ['top','right','bottom','left']:
                sv = styles.get(side)
                if sv:
                    m = re.match(r'(-?\d+(?:\.\d+)?)(px|%|vh|vw)?', sv)
                    if m: s[f"position_{side}"] = {"unit":m.group(2) or "px","size":float(m.group(1))}
            zi = styles.get('z-index')
            if zi:
                try: s["z_index"] = int(zi)
                except ValueError: pass

        # Min/Max height
        for prop, key in [('min-height','min_height'),('max-height','max_height'),('height','height')]:
            hv = styles.get(prop)
            if hv:
                m = re.match(r'(\d+(?:\.\d+)?)(px|%|vh|vw|em|rem)?', hv)
                if m: s[key] = {"unit":m.group(2) or "px","size":float(m.group(1))}

        # CSS Transform → Elementor _transform
        transform = styles.get('transform')
        if transform and transform != 'none':
            tx = re.search(r'translateX\((-?[\d.]+)(px|%)?\)', transform)
            ty = re.search(r'translateY\((-?[\d.]+)(px|%)?\)', transform)
            rot = re.search(r'rotate\((-?[\d.]+)deg\)', transform)
            sc = re.search(r'scale\(([\d.]+)\)', transform)
            if tx or ty or rot or sc:
                s["_transform_translate_popover"] = ""
                s["motion_fx_motion_fx_scrolling"] = ""
            if tx: s["_transform_translateX"] = {"unit":tx.group(2) or "px","size":float(tx.group(1))}
            if ty: s["_transform_translateY"] = {"unit":ty.group(2) or "px","size":float(ty.group(1))}
            if rot: s["_transform_rotate"] = {"unit":"deg","size":float(rot.group(1))}
            if sc: s["_transform_scale"] = {"unit":"","size":float(sc.group(1))}

        if custom_css_val:
            s["custom_css"] = custom_css_val

        # Compile children
        elements_json = []
        for child in direct_children:
            cc = compile_element(child, css_rules, pseudo_rules, soup, cache, depth + 1)
            if cc: elements_json.append(cc)

        return {
            "id": generate_id(), "elType": "container", "settings": s,
            "elements": elements_json, "isInner": depth > 0  # ← proper isInner
        }
    else:
        # --- WIDGET ---
        ws = {"_element_id": generate_id()}
        if custom_css_val:
            ws["custom_css"] = custom_css_val
        align = styles.get('text-align', 'left')
        at = tab_styles.get('text-align'); am = mob_styles.get('text-align')

        if css_classes_str: ws["css_classes"] = css_classes_str; ws["_css_classes"] = css_classes_str
        if css_id: ws["css_id"] = css_id; ws["_css_id"] = css_id

        ws["_padding"] = get_padding_or_margin(styles, 'padding')
        ws["_margin"] = get_padding_or_margin(styles, 'margin')
        pt = get_padding_or_margin(tab_styles, 'padding')
        if has_nonzero(pt): ws["_padding_tablet"] = pt
        pm = get_padding_or_margin(mob_styles, 'padding')
        if has_nonzero(pm): ws["_padding_mobile"] = pm
        mt = get_padding_or_margin(tab_styles, 'margin')
        if has_nonzero(mt): ws["_margin_tablet"] = mt
        mm = get_padding_or_margin(mob_styles, 'margin')
        if has_nonzero(mm): ws["_margin_mobile"] = mm

        wt = "text-editor"

        if tag in ['h1','h2','h3','h4','h5','h6']:
            wt = "heading"
            ws.update({"title":element.get_text(strip=True),"header_size":tag,"align":align,"title_color":get_color(styles,'color')})
            if at: ws["align_tablet"] = at
            if am: ws["align_mobile"] = am
            ws.update(get_typography(styles))
            tt = get_typography(tab_styles)
            if "typography_font_size" in tt: ws["typography_font_size_tablet"] = tt["typography_font_size"]
            tm = get_typography(mob_styles)
            if "typography_font_size" in tm: ws["typography_font_size_mobile"] = tm["typography_font_size"]

        elif tag == 'img':
            wt = "image"
            ws.update({"image":{"url":element.get('src',''),"id":"","size":""},"image_size":"full","align":align or "center"})
            alt = element.get('alt')
            if alt: ws["caption"] = alt
            if at: ws["align_tablet"] = at
            if am: ws["align_mobile"] = am

        elif tag in ['a','button'] or any('btn' in c for c in classes):
            wt = "button"
            url = element.get('href', '#') if tag == 'a' else '#'
            ws.update({"text":element.get_text(strip=True),
                       "link":{"url":url,"is_external":"","nofollow":"","custom_attributes":""},
                       "align":align or "left","button_text_color":get_color(styles,'color')})
            if at: ws["align_tablet"] = at
            if am: ws["align_mobile"] = am
            bgs = get_background(styles)
            if "background_color" in bgs: ws["background_color"] = bgs["background_color"]
            ws.update(get_typography(styles))
            br = styles.get('border-radius')
            if br:
                m = re.match(r'(\d+(?:\.\d+)?)(px|%|rem)?', br)
                if m:
                    r = m.group(1)
                    ws["border_radius"] = {"unit":m.group(2) or "px","top":r,"right":r,"bottom":r,"left":r,"isLinked":True}

        elif tag == 'i' or (tag == 'span' and any(c.startswith('fa-') or c in ['fa','fas','fab','far','fal','fad'] for c in classes)):
            wt = "icon"
            icon_val, icon_lib = detect_icon_library(classes)
            if not icon_val: icon_val = "fas fa-star"; icon_lib = "fa-solid"
            ws.update({"icon":{"value":icon_val,"library":icon_lib},"view":"default","shape":"circle","align":align or "center"})
            ic = get_color(styles, 'color')
            if ic: ws["primary_color"] = ic

        elif tag == 'video':
            wt = "video"
            src_tag = element.find('source')
            vurl = src_tag.get('src','') if src_tag else element.get('src','')
            ws.update({"video_type":"hosted","insert_url":"yes","external_url":vurl,
                       "loop":"yes" if element.has_attr('loop') else "",
                       "autoplay":"yes" if element.has_attr('autoplay') else "",
                       "mute":"yes" if element.has_attr('muted') else ""})

        elif (tag in ['ul','ol']) and len(direct_children) > 0 and all(c.name == 'li' for c in direct_children):
            wt = "icon-list"
            items = []
            for li in direct_children:
                ni = li.find('i')
                icon = "fas fa-circle"
                if ni:
                    iv, il = detect_icon_library(ni.get('class', []))
                    if iv: icon = iv
                items.append({"text":li.get_text(strip=True),"selected_icon":{"value":icon,"library":"fa-solid"}})
            ws.update({"icon_list":items})

        elif tag == 'iframe':
            src = element.get('src', '')
            if 'maps.google' in src or 'google.com/maps' in src:
                wt = "google_maps"
                ws.update({"address":"","zoom":{"unit":"px","size":10},"height":{"unit":"px","size":350}})
            elif 'youtube' in src or 'vimeo' in src:
                wt = "video"
                ws.update({"video_type":"youtube" if 'youtube' in src else "vimeo","youtube_url":src,"vimeo_url":src})
            else:
                wt = "html"
                ws.update({"html":str(element)})

        elif tag == 'svg':
            wt = "html"
            ws.update({"html":str(element)})

        else:
            wt = "text-editor"
            inner = "".join(str(c) for c in element.contents).strip()
            ws.update({"editor":inner,"align":align,"text_color":get_color(styles,'color')})
            if at: ws["align_tablet"] = at
            if am: ws["align_mobile"] = am
            ws.update(get_typography(styles))
            tt = get_typography(tab_styles)
            if "typography_font_size" in tt: ws["typography_font_size_tablet"] = tt["typography_font_size"]
            tm = get_typography(mob_styles)
            if "typography_font_size" in tm: ws["typography_font_size_mobile"] = tm["typography_font_size"]

        return {"id":generate_id(),"elType":"widget","widgetType":wt,"settings":ws,"elements":[]}

# ---------------------------------------------------------------------------
# Main Compiler
# ---------------------------------------------------------------------------
def compile_html(html_str, base_dir=None):
    global _selector_cache
    soup = BeautifulSoup(html_str, 'html.parser')
    cache = SelectorCache()

    # Gather CSS: inline <style> + external <link>
    css_content = ""
    for st in soup.find_all('style'):
        if st.string: css_content += st.string + "\n"

    if base_dir:
        ext_css = fetch_external_stylesheets(soup, base_dir)
        if ext_css:
            css_content = ext_css + "\n" + css_content
            print(f"  Fetched {len(ext_css)} chars of external CSS")

    css_vars = extract_css_variables(css_content)
    if css_vars:
        print(f"  Resolved {len(css_vars)} CSS variables")

    css_rules, _ = parse_css_cascade(css_content, css_vars)
    print(f"  Parsed {len(css_rules)} CSS rules")

    pseudo_rules = extract_pseudo_and_state_rules(css_content, css_vars)
    keyframes_content = extract_keyframes(css_content)

    body = soup.find('body')
    body_color = '#ffffff'
    if body:
        rb = resolve_full_styles(body, css_rules, soup, cache)
        bg = get_background(rb['desktop'])
        body_color = bg.get('background_color', '#ffffff')

    elements = []
    root = body or soup
    for child in root.children:
        if child.name is not None:
            c = compile_element(child, css_rules, pseudo_rules, soup, cache, depth=0)
            if c: elements.append(c)

    cleaned_css = re.sub(r'body\s*\{[^}]*\}', '', css_content)
    if keyframes_content:
        cleaned_css = keyframes_content + "\n" + cleaned_css

    return {
        "content": elements,
        "page_settings": {
            "background_background": "classic",
            "background_color": body_color,
            "custom_css": cleaned_css.strip()
        },
        "version": "0.4",
        "title": "Compiled Elementor Page Template",
        "type": "page"
    }

# ---------------------------------------------------------------------------
# WordPress Asset Uploader
# ---------------------------------------------------------------------------
def upload_to_wordpress(file_path, wp_url, username, password):
    if not os.path.exists(file_path):
        print(f"  Warning: Asset not found: {file_path}")
        return None
    fname = os.path.basename(file_path)
    mime, _ = mimetypes.guess_type(file_path)
    mime = mime or 'image/jpeg'
    with open(file_path, 'rb') as f: data = f.read()
    url = f"{wp_url.rstrip('/')}/wp/v2/media"
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {'Content-Type':mime,'Content-Disposition':f'attachment; filename="{fname}"','Authorization':f'Basic {auth}'}
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            rd = json.loads(resp.read().decode())
            print(f"  Uploaded: {fname} -> {rd.get('source_url')}")
            return {"url":rd.get('source_url'),"id":rd.get('id')}
    except Exception as e:
        print(f"  Upload error ({fname}): {e}")
        return None

def process_json_assets(obj, wp_url, user, pw, base_dir):
    if isinstance(obj, dict):
        if "url" in obj and obj["url"] and not obj["url"].startswith(('http://','https://','data:')):
            lp = obj["url"]
            if not os.path.isabs(lp): lp = os.path.join(base_dir, lp)
            r = upload_to_wordpress(lp, wp_url, user, pw)
            if r: obj["url"] = r["url"]; obj["id"] = r["id"]
        else:
            for v in obj.values(): process_json_assets(v, wp_url, user, pw, base_dir)
    elif isinstance(obj, list):
        for i in obj: process_json_assets(i, wp_url, user, pw, base_dir)

def resolve_relative_urls(obj, base_url):
    """Prepend base_url to relative paths recursively."""
    if not base_url:
        return
    base_url = base_url.rstrip('/') + '/'
    if isinstance(obj, dict):
        if "url" in obj and isinstance(obj["url"], str) and obj["url"]:
            u = obj["url"].strip()
            if not u.startswith(('http://', 'https://', 'data:', '//')):
                obj["url"] = base_url + u.lstrip('/')
        if "external_url" in obj and isinstance(obj["external_url"], str) and obj["external_url"]:
            u = obj["external_url"].strip()
            if not u.startswith(('http://', 'https://', 'data:', '//')):
                obj["external_url"] = base_url + u.lstrip('/')
        for v in obj.values():
            resolve_relative_urls(v, base_url)
    elif isinstance(obj, list):
        for i in obj:
            resolve_relative_urls(i, base_url)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTML to Elementor JSON Compiler (Best-in-Market)")
    parser.add_argument("input_html", help="Input HTML file path")
    parser.add_argument("output_json", help="Output Elementor JSON template path")
    parser.add_argument("--wp-url", help="WordPress REST API base URL")
    parser.add_argument("--wp-user", help="WordPress username")
    parser.add_argument("--wp-pass", help="WordPress application password")
    parser.add_argument("--base-asset-url", help="Prepend this URL to relative image/video assets")
    args = parser.parse_args()

    if not os.path.exists(args.input_html):
        print(f"Error: '{args.input_html}' not found."); sys.exit(1)

    print(f"Reading HTML from {args.input_html}...")
    with open(args.input_html, 'r', encoding='utf-8') as f: html = f.read()

    base_dir = os.path.dirname(os.path.abspath(args.input_html))
    print("Compiling (CSS cascade + Tailwind JIT + Bootstrap + Pro widgets)...")
    template = compile_html(html, base_dir)

    if args.wp_url and args.wp_user and args.wp_pass:
        print("Uploading assets to WordPress...")
        process_json_assets(template, args.wp_url, args.wp_user, args.wp_pass, base_dir)

    if args.base_asset_url:
        print(f"Resolving relative asset URLs to base: {args.base_asset_url}...")
        resolve_relative_urls(template, args.base_asset_url)

    print(f"Writing to {args.output_json}...")
    with open(args.output_json, 'w', encoding='utf-8') as f: json.dump(template, f, indent=4)

    # Summary
    def count_elements(content):
        c = w = 0
        for el in content:
            if el.get('elType') == 'container': c += 1
            elif el.get('elType') == 'widget': w += 1
            cc, ww = count_elements(el.get('elements', []))
            c += cc; w += ww
        return c, w
    containers, widgets = count_elements(template['content'])
    print(f"\nDone! {containers} containers + {widgets} widgets compiled.")
